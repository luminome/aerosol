#!/usr/bin/env python3
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtSvg import *
from lxml import etree
import time
import math
import re

rx_dict = {
    'translate': re.compile(r'translate\((?P<translate>[\d.\s]+)\)'),
    'scale': re.compile(r'scale\((?P<scale>[\d.\s]+)\)'),
    'rotate': re.compile(r'rotate\((?P<rotate>[\d.\s]+)\)'),
    'matrix': re.compile(r'matrix\((?P<matrix>[-\d.\s]+)\)')
}


class ItemAnim(QPointF):
    def __init__(self, parent=None):
        super(ItemAnim, self).__init__()
        self.item = parent
        self.p1 = QPointF()
        self.p2 = QPointF()
        self.rate = 120.0
        self.is_animating = False
        self.tct = 0

    def easeInOutSine(self, t, b, c, d):
        return -c / 2 * (math.cos(math.pi * t / d) - 1) + b

    """
    t is the current time (or position) of the tween.
    b is the beginning value of the property.
    c is the change between the beginning and destination value of the property.
    d is the total time of the tween.
    """

    def idle(self):
        a = float((self.p1.x() - self.p2.x()))
        b = float((self.p1.y() - self.p2.y()))
        d = math.sqrt(pow(a, 2) + pow(b, 2))

        if not self.is_animating:
            self.tct = 0
        else:
            self.tct += 1

        arp = self.easeInOutSine(self.tct, 0, 2, self.rate*2)
        self.is_animating = d > 0.005

        if self.is_animating:
            x = float(self.x()) - float(a * arp)  #arp.x()  #(a / self.rate)  # - a*math.sin(1/d)
            y = float(self.y()) - float(b * arp)  #(b / self.rate)  # - b*math.sin(1/d)
            self.setX(x)
            self.setY(y)
            self.p1 = QPointF(x, y)
            self.item.update_pos()


class SvgLayer(QGraphicsSvgItem):
    def __init__(self, parent=None):
        super(SvgLayer, self).__init__()
        self.ds = None
        self.scale_s = 0.0
        self.center_x = 0
        self.center_y = 0
        self.defViewBox = None
        self.parent = parent
        self.size = None
        self.width = None
        self.height = None
        self.usage_type = None
        self.size = self.boundingRect()
        self.width = self.size.width()
        self.height = self.size.height()
        self.transform = QTransform()
        self.animator = ItemAnim(self)
        self.origin = None

    def get_center_pos(self):
        d = self.boundingRect()
        m = self.transform.map(0, 0)
        c = QPointF(d.width() / 2, d.height() / 2)
        g = QPointF(m[0], m[1])
        return c + g

    def get_center_pos_scene(self):
        sd = self.sceneBoundingRect()
        sp = self.scenePos() + (QPointF(sd.width() / 2, sd.height() / 2))
        return sp

    def update_pos(self):
        self.center_x = float(self.animator.p1.x() - self.origin.x())
        self.center_y = float(self.animator.p1.y() - self.origin.y())
        self.update_view(self.size)

    def load_item(self):
        print('loaded')
        m = self.transform.map(0, 0)
        self.size = self.boundingRect()
        self.width = self.size.width()
        self.height = self.size.height()
        self.origin = QPointF(m[0], m[1])
        self.animator.p1 = self.origin
        self.animator.p2 = self.origin
        self.scale_s = 0.5
        self.setScale(self.scale_s)
        self.center_x = float(self.size.width() / 2.0)*self.scale_s  #.x()
        self.center_y = float(self.size.height() / 2.0)*self.scale_s  #.y()
        self.update_view()

    def update_view(self):
        s = self.boundingRect()
        w = self.scale() * s.width()
        h = self.scale() * s.height()
        c = QPointF(self.center_x - w / 2.0, self.center_y - h / 2.0)
        self.setPos(c)

    def center(self, size):
        self.scale_s = float(size.height()) / self.height
        self.setScale(self.scale_s)
        self.center_x = float(size.width() / 2.0)  #.x()
        self.center_y = float(size.height() / 2.0)  #.y()
        self.update_view()

    def zoom(self, evt):
        mouse_angle = evt.angleDelta().y()
        z = self.mapFromScene(evt.pos())
        dx = z.x() - self.width / 2
        dy = z.y() - self.height / 2
        center_x = self.center_x + dx * self.scale_s
        center_y = self.center_y + dy * self.scale_s
        self.scale_s = self.scale_s * 1.0025 ** (-mouse_angle)
        self.setScale(self.scale_s)

        self.center_x = center_x - dx * self.scale_s
        self.center_y = center_y - dy * self.scale_s

        self.animator.setX(self.center_x)
        self.animator.setY(self.center_y)

        self.update_view()


class SvgLand(QGraphicsView):  #QSvgWidget):
    location_changed = pyqtSignal(QPointF)
    keymap = {}
    for key, value in vars(Qt).items():
        if isinstance(value, Qt.Key):
            keymap[value] = key.partition('_')[2]

    keymap_modifiers = {
        Qt.ControlModifier: keymap[Qt.Key_Control],
        Qt.AltModifier: keymap[Qt.Key_Alt],
        Qt.ShiftModifier: keymap[Qt.Key_Shift],
        Qt.MetaModifier: keymap[Qt.Key_Meta],
        Qt.GroupSwitchModifier: keymap[Qt.Key_AltGr],
        Qt.KeypadModifier: keymap[Qt.Key_NumLock],
    }

    def __init__(self, parent=None):
        super(SvgLand, self).__init__(parent)
        self.renderer = None
        self.svgItem = None
        self.massive = None
        self.anchor_layer = QGraphicsSvgItem()
        self.anchor_translating = None
        self.dims_offset = QSizeF()
        self.dims_viewport = QRectF()
        self.dims_viewport_raw = QRectF()
        self.dims_limit = None
        self.dims_page = None
        self.dims_center = None
        self.parent = parent
        self.click_start = None
        self.start_center_x = 0.0
        self.start_center_y = 0.0
        self.frame = 0
        self.fps_average = (0.0,)
        self.paint_time = 0.0
        self.paint_time_delta = 1
        self.showShort = None
        self.new_loc = None
        self.plush = None
        self.index = 0
        self.paint_fps = None
        self.rel_mouse = None

        tile_pixmap = QPixmap(100, 100)
        tile_pixmap.fill(Qt.white)
        tile_painter = QPainter(tile_pixmap)
        color = QColor(250, 250, 250)
        tile_painter.fillRect(0, 0, 50, 50, color)
        tile_painter.fillRect(50, 50, 50, 50, color)
        tile_painter.end()

        self.setBackgroundBrush(QBrush(tile_pixmap))
        self.setScene(QGraphicsScene(self))
        self.setContentsMargins(0, 10, 0, 0)
        self.setMouseTracking(True)
        self.setPalette(QPalette(Qt.white))
        self.setAutoFillBackground(True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    #naarate
    def set_item_index(self, dir=1):
        self.index += dir
        select_a = [a for a in self.anchor_layer.childItems()]
        if self.index >= len(select_a):
            self.index = 0
        elif self.index < 0:
            self.index = len(select_a) - 1

        index_item = select_a[self.index]
        print(self.index, index_item, index_item.elementId())
        self.svg_move_to_index(index_item)

    #make an SvgLayer:QGraphicsSvgItem
    def make_svg_item(self, item_id):
        #requires self.renderer
        h = SvgLayer(self)
        h.setSharedRenderer(self.renderer)
        h.setElementId(item_id)
        h.setFlags(QGraphicsItem.ItemClipsToShape)
        h.setCacheMode(QGraphicsItem.NoCache)
        h.setZValue(1)
        return h

    #apply_transform takes extant_svg_xml and returns a QTransform()
    def node_transform(self, xml_node):
        mtrans = xml_node.get('transform')
        tranox = {}

        if mtrans is not None:
            print(xml_node.get('id'), "node_transform", xml_node.attrib)
            for key, rx in rx_dict.items():
                match = rx.search(mtrans)
                if match:
                    e = [float(n) for n in match.group(key).split(' ')]
                    tranox[key] = e

        transform = QTransform()

        if 'translate' in tranox:
            translate = tranox['translate']
        else:
            translate = [0, 0]

        if 'rotate' in tranox:
            print('rotated', xml_node.attrib)

        if 'matrix' in tranox:
            matrix = tranox['matrix']
        else:
            matrix = [1, 0, 0, -1, translate[0], translate[1]]

        print(matrix)
        attributes_copy = ['width', 'height', 'x', 'y']  #, 'x', 'y']

        apos = {'matrix': matrix}  #[1, 0, 0, -1, matrix[0], matrix[1]]}

        for n in attributes_copy:
            apos[n] = float(xml_node.get(n))

        x_offset = (apos["x"] * matrix[0])  #0  #(apos["width"]/ 2)  #*matrix[0]   #apos["x"] * float(matrix[0]) + self.dims_offset.width()
        y_offset = (apos["y"] * matrix[0])  # 0 #apos["y"] * abs(float(matrix[3])) + self.dims_offset.height()

        m11 = float(matrix[0])  #m11() // Horizontal scaling
        m12 = transform.m12()  ##;    // Vertical shearing
        m13 = float(matrix[1])  ##;    // Horizontal Projection
        m21 = transform.m21()  ##;    // Horizontal shearing
        m22 = abs(float(matrix[3]))  #m22() // vertical scaling
        m23 = float(matrix[2])  #m23() // Vertical Projection
        m31 = float(matrix[4]) + x_offset  #m31() // Horizontal Position (DX) (with centered offset)
        m32 = float(matrix[5]) + y_offset  #m32() // Vertical Position (DY) (with centered offset)
        m33 = transform.m33()  ##;    // Additional Projection Factor

        transform.setMatrix(m11, m12, m13, m21, m22, m23, m31, m32, m33)
        return transform

    def load(self, path):
        svg_source = QFile(path)
        if not svg_source.exists():
            return

        svg_source_file = svg_source.fileName()
        svg_filter_file = svg_source.fileName().split('.')[0] + '-filtered.svg'
        scene = self.scene()
        #// MODIFY STRUCTURE OF SOURCE SVG
        # tree = ElementTree.parse(svg_source_file)
        # root = tree.getroot()

        tree = etree.parse(svg_source_file)
        root = tree.getroot()

        symbols = {}
        namespace = "{http://www.w3.org/2000/svg}"
        svg_item_copied_attributes = ['x', 'y', 'width', 'height', 'transform']
        #//<use width="20" height="20" transform="translate(7873.71765 1139.40743)" xlink:href="#num_12"/>
        symbols_layer = etree.SubElement(root, '{0}g'.format(namespace))
        symbols_layer.set('id', 'symbols_layer')

        for symbol in root.findall('.//{0}symbol'.format(namespace)):
            symbols[symbol.get("id")] = symbol

        #//TODO: alert this
        all_uses = root.findall('.//*{0}use'.format(namespace))

        for use in all_uses:
            uid = use.get('{http://www.w3.org/1999/xlink}href')
            par = use.getparent()
            symbol = root.findall(".//*[@id='%s']" % str(uid[1:]))[0]
            symbol_fax = etree.SubElement(par, 'g')
            symbol_fax.set('id', str(uid[1:]))

            if symbol.tag == '{0}symbol'.format(namespace):
                for att in svg_item_copied_attributes:
                    symbol_fax.set(att, use.get(att))
                for g in symbol:
                    symbol_fax.append(g)

                root.remove(symbol)
                symbols_layer.append(symbol_fax)

            par.remove(use)

        tree.write(svg_filter_file)
        print('supersede')

        #// APPLY SOURCE SVG to SvgLand(QGraphicsView)
        self.renderer = QSvgRenderer(svg_filter_file)  #svg_filter_file)

        print('renderer set')

        #self.anchor_layer = self.make_svg_item('anchor')
        self.anchor_layer = SvgLayer(self)
        self.anchor_layer.setSharedRenderer(self.renderer)
        self.anchor_layer.setCacheMode(QGraphicsItem.NoCache)  #$NoCache)
        self.anchor_layer.setFlags(QGraphicsItem.ItemClipsChildrenToShape)

        self.dims_limit = QSizeF(self.renderer.defaultSize())
        self.dims_page = QSizeF(self.anchor_layer.boundingRect().size())
        self.dims_offset = (self.dims_page - self.dims_limit) / 2.0

        self.dims_viewport_raw = self.viewport().rect()  #//d
        self.dims_viewport = self.mapToScene(self.dims_viewport_raw).boundingRect()  #//r
        scene.setSceneRect(QRectF(self.dims_viewport_raw))

        for layer in root.findall('{0}g'.format(namespace)):
            print('main', layer.get("id"))

            if layer.get('id') == 'symbols_layer':
                symbols_converted = layer.findall('g')

                for symbol in symbols_converted:
                    print(symbol.get('id'))
                    symbol_transform = self.node_transform(symbol)
                    created_symbol_item = self.make_svg_item(symbol.get('id'))
                    created_symbol_item.setTransform(symbol_transform)
                    created_symbol_item.transform = symbol_transform
                    created_symbol_item.usage_type = 'waypoint'
                    created_symbol_item.setParentItem(self.anchor_layer)

                    if symbol.get('id') == 'plush':
                        self.plush = created_symbol_item
            else:
                pass
                # created_layer_item = self.make_svg_item(layer.get("id"))
                # if layer.get('class') == '.hidden':
                #     created_layer_item.hide()
                # created_layer_item.usage_type = 'layer-area'
                # created_layer_item.setParentItem(self.anchor_layer)
                # scene.addItem(created_layer_item) #self.anchor_layer)

        scene.addItem(self.anchor_layer)

        self.anchor_layer.load_item()
        #self.anchor_layer.center(self.dims_viewport)

        self.plush.load_item()

        self.plush.animator.rate = 60  #()

    def svg_move_to(self, loc: QPointF, relative=False):
        #//map to self coords
        if relative:
            delta = loc * self.anchor_layer.scale_s
        else:
            delta = loc

        self.anchor_layer.center_x += delta.x()
        self.anchor_layer.center_y += delta.y()
        self.anchor_layer.update_view()

    def svg_move_to_index(self, index_item):
        self.plush.animator.tct = 0
        self.plush.animator.p2 = index_item.get_center_pos()
        aq = self.anchor_layer.mapFromParent(self.dims_center)
        bq = index_item.get_center_pos()
        cq = (aq - bq)
        ct = QPointF(self.anchor_layer.center_x, self.anchor_layer.center_y)
        self.anchor_layer.animator.p2 = ct + cq * self.anchor_layer.scale()
        self.anchor_layer.animator.tct = 0

    def wheelEvent(self, evt):
        if not self.anchor_translating:
            self.anchor_layer.zoom(evt)

    def mousePressEvent(self, evt):
        interact = self.itemAt(evt.pos())

        if hasattr(interact, 'elementId') and hasattr(interact, 'usage_type'):
            self.parent.set_status('CLICK %s %s' % (interact.usage_type, interact.elementId()))

        op = QPointF(self.anchor_layer.mapFromParent(evt.pos()))
        self.plush.animator.p2 = op

        if hasattr(interact, 'elementId') and hasattr(interact, 'usage_type'):
            if interact.usage_type == 'waypoint' and interact.elementId() != 'plush':
                self.svg_move_to_index(interact)

        if evt.button() == Qt.LeftButton and interact is not None:
            if not self.anchor_layer.animator.is_animating:
                self.click_start = evt.pos()
                self.start_center_x = self.anchor_layer.center_x
                self.start_center_y = self.anchor_layer.center_y
                self.anchor_translating = evt.pos()
        else:
            super(SvgLand, self).mousePressEvent(evt)

    def mouseMoveEvent(self, evt):
        #self.updateLocation(evt.pos())
        flag = ''
        if self.anchor_translating:
            if not self.anchor_layer.animator.is_animating:
                a_pos = evt.pos()
                dx = self.anchor_translating.x() - a_pos.x()
                dy = self.anchor_translating.y() - a_pos.y()
                self.anchor_layer.center_x = self.start_center_x - dx
                self.anchor_layer.center_y = self.start_center_y - dy
                self.anchor_layer.update_view()

                ct = QPointF(self.anchor_layer.center_x, self.anchor_layer.center_y)
                self.anchor_layer.animator.setX(self.anchor_layer.center_x)
                self.anchor_layer.animator.setY(self.anchor_layer.center_y)
                #print(ct)

                flag = 'translating'

        interact = self.itemAt(evt.pos())
        if interact:
            op = QPointF(self.anchor_layer.mapFromParent(evt.pos()))
            self.rel_mouse = ('X %i Y %i %s' % (op.x(), op.y(), flag))
        else:
            self.rel_mouse = ('VOID %s' % flag)

    def mouseReleaseEvent(self, evt):
        if evt.button() == Qt.LeftButton:
            self.mouseMoveEvent(evt)
            self.anchor_translating = None

    def key_event_to_string(self, event):
        sequence = []
        for modifier, text in self.keymap_modifiers.items():
            if event.modifiers() & modifier:
                sequence.append(text)
        key = self.keymap.get(event.key(), event.text())
        if key not in sequence:
            sequence.append(key)
        return sequence

    def event(self, event):
        if event.type() == QEvent.KeyPress:
            keys = self.key_event_to_string(event)
            self.parent.set_status('+'.join(keys))

            if 'Space' in keys:
                self.anchor_layer.center(self.dims_viewport)
                print('space')

            if 'Up' in keys:
                self.svg_move_to(QPointF(0.0, -300.0), True)

            if 'Down' in keys:
                self.svg_move_to(QPointF(0.0, 300.0), True)

            if 'A' in keys:
                self.set_item_index(dir=-1)

            if 'D' in keys:
                self.set_item_index(dir=1)
            return True

        #super(MainWindow, self).event(event)
        return QGraphicsView.event(self, event)

    def resizeEvent(self, evt):
        self.dims_viewport_raw = self.viewport().rect()
        self.dims_viewport = self.mapToScene(self.dims_viewport_raw).boundingRect()
        self.dims_center = QPointF(self.dims_viewport_raw.width() / 2, self.dims_viewport_raw.height() / 2)

    def util_paint_timer(self):
        delta = self.paint_time_delta
        fms = (1 / delta)
        n = tuple(self.fps_average)
        a = (fms + sum(n)) / 10

        if n[-1] != fms:
            n = n + (fms,)

        if len(n) > 10:
            n = n[1:]

        self.fps_average = n
        seconds = int(time.time() % 60)

        self.paint_fps = '%02i | %d paints/sec' % (seconds, a)
        #self.parent.set_status()

    def paintEvent(self, evt):
        self.paint_time = time.time()
        super(SvgLand, self).paintEvent(evt)
        self.util_paint_timer()
        self.paint_time_delta = time.time() - self.paint_time  #this is seconds


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.tick_counter = 0
        self.tick_time_counter = 0
        self.frame_counter = 0
        self.time_counter = 0
        self.seconds = 0

        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)

        status_bar_style = '; '.join([
            'background-color: black',
            'height:10px',
            'color:yellow'
        ])

        self.statusbar.setStyleSheet(status_bar_style)
        self.statusBar().setFont(QFont('Helvetica', 10))
        self.statusbar.showMessage('hello.')

        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("central_widget")
        self.viewer = SvgLand(self)
        self.viewer.setFrameShape(QFrame.NoFrame)

        # set the layout to centralWidget
        layout = QGridLayout(self.central_widget)
        # add the viewer to the layout
        layout.addWidget(self.viewer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setCentralWidget(self.central_widget)
        self.setWindowTitle("AEROSOL Svg Viewer")

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(0)

        self.resize(1024, 554)
        self.show()

    def set_status(self, s_str):
        self.statusbar.showMessage(self.viewer.paint_fps+self.viewer.rel_mouse+s_str)

    def show_location(self, pt):
        self.statusbar.showMessage("%f %f" % (pt.x(), pt.y()))

    def open(self, svg_file_path):
        self.viewer.load(svg_file_path)

    def update_frame(self):

        if self.viewer.plush:
            self.viewer.plush.animator.idle()

        if self.viewer.anchor_layer:
            self.viewer.anchor_layer.animator.idle()

        try:
            self.tick_counter += 1
            tick = int(round(time.time() * 1000) / 100)
            self.frame_counter += 1
            seconds = int(time.time() % 60)

            if tick != self.tick_time_counter:
                self.viewer.util_paint_timer()
                self.tick_time_counter = tick
                self.tick_counter = 0

            if seconds != self.time_counter:
                self.time_counter = seconds
                self.frame_counter = 0

        except KeyboardInterrupt:
            print('KeyboardInterrupt W T F, use QUIT')


if __name__ == '__main__':

    import sys

    app = QApplication(sys.argv)
    window = MainWindow()

    if len(sys.argv) == 2:
        window.open(sys.argv[1])
    else:
        print('no file?')
        exit()

    window.show()
    sys.exit(app.exec_())