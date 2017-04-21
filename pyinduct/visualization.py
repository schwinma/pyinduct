"""
Here are some frequently used plot types with the packages :py:mod:`pyqtgraph` and/or :py:mod:`matplotlib` implemented.
The respective :py:mod:`pyinduct.visualization` plotting function get an :py:class:`EvalData` object whose definition
also placed in this module.
A :py:class:`EvalData`-object in turn can easily generated from simulation data.
The function :py:func:`pyinduct.simulation.simulate_system` for example already provide the simulation result
as EvalData object.
"""

import numpy as np
import time
import os
import scipy.interpolate as si
import pyqtgraph as pg
import pyqtgraph.exporters
import pyqtgraph.opengl as gl
from pyqtgraph.pgcollections import OrderedDict

from numbers import Number
# Axes3D not explicit used but needed
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib as mpl
from pyinduct.tests import show_plots

from .core import complex_wrapper, EvalData, Domain
from .utils import create_animation, create_dir

__all__ = ["show", "create_colormap", "PgAnimatedPlot", "PgSurfacePlot",
           "PgLinePlot2d", "PgAdvancedViewWidget", "PgColorBarWidget",
           "PgGradientWidget", "MplSurfacePlot", "MplSlicePlot",
           "visualize_roots", "visualize_functions"]

colors = ["g", "c", "m", "b", "y", "k", "w", "r"]
color_map = "viridis"


# pg.setConfigOption('background', 'w')
# pg.setConfigOption('foreground', 'k')


def show(show_pg=True, show_mpl=True, force=False):
    """
    Shortcut to show all pyqtgraph and matplotlib plots / animations.

    Args:
        show_pg (bool): Show matplotlib plots? Default: True
        show_mpl (bool): Show pyqtgraph plots? Default: True
        force (bool): Show plots even during unittest discover, setup
            and so on? Default: False
    """
    if show_plots or force:
        if show_pg:
            pg.QtGui.QApplication.instance().exec_()

        if show_mpl:
            plt.show()


def create_colormap(cnt):
    """
    Create a colormap containing cnt values.

    Args:
        cnt (int):

    Return:
        Colormap ...
    """
    col_map = pg.ColorMap(np.array([0, .5, 1]),
                          np.array([[0, 0, 1., 1.], [0, 1., 0, 1.], [1., 0, 0, 1.]]))
    indexes = np.linspace(0, 1, cnt)
    return col_map.map(indexes, mode="qcolor")


def visualize_functions(functions, points=100):
    """
    Visualizes a set of :py:class:`core.Function` s on
    their domain.

    Parameters:
        functions (iterable): collection of
            :py:class:`core.Function` s to display.
        points (int): Points to use for sampling
            the domain.
    """
    # evaluate
    _data = []
    for idx, func in enumerate(functions):
        if len(func.domain) > 1:
            # TODO support funcs with multiple domains
            raise NotImplementedError

        dom = Domain(bounds=func.domain[0], num=points)
        val = func(dom)
        _data.append((dom, np.real(val), np.imag(val)))

    data = np.array(_data)

    # plot
    cmap = cm.get_cmap(color_map)
    pg.mkQApp()
    pw = pg.GraphicsLayoutWidget()
    pw.setWindowTitle("function set visualization")

    lbl = pg.LabelItem(text="Real Part",
                       angle=-90,
                       bold=True,
                       size="10pt")
    pw.addItem(lbl)

    p_real = pg.PlotItem()
    p_real.addLegend()
    for idx, row in enumerate(data):
        c = cmap(idx / len(functions), bytes=True)
        p_real.plot(row[0], row[1],
                    name="vector {}".format(idx),
                    pen=c)
    pw.addItem(p_real)

    if not np.allclose(data[:, 2, :], 0):
        # complex data is present
        pw.nextRow()
        lbl = pg.LabelItem(text="Imaginary Part",
                           angle=-90,
                           bold=True,
                           size="10pt")
        pw.addItem(lbl)

        p_imag = pg.PlotItem()
        # p_imag.addLegend()
        for idx, row in enumerate(data):
            c = cmap(idx / len(functions), bytes=True)
            p_imag.plot(row[0], row[2],
                        name="vector {}".format(idx),
                        pen=c)
        pw.addItem(p_imag)

    pw.show()
    pg.QAPP.exec_()


class DataPlot:
    """
    Base class for all plotting related classes.
    """

    def __init__(self, data):

        # just to be sure
        assert isinstance(data, list) or isinstance(data, EvalData)
        if isinstance(data, EvalData):
            data = [data]
        else:
            assert isinstance(data[0], EvalData)

        self._data = data
        # TODO Test input vectors to be Domain objects and use
        # their .step attribute here
        self._dt = data[0].input_data[0][1] - data[0].input_data[0][0]


class PgDataPlot(DataPlot, pg.QtCore.QObject):
    """
    Base class for all pyqtgraph plotting related classes.
    """

    def __init__(self, data):
        DataPlot.__init__(self, data)
        pg.mkQApp()
        pg.QtCore.QObject.__init__(self)


class PgAnimatedPlot(PgDataPlot):
    """
    Wrapper that shows an updating one dimensional plot of n-curves discretized in t time steps and z spatial steps
    It is assumed that time propagates along axis0 and and location along axis1 of values.
    values are therefore expected to be a array of shape (n, t, z)

    Args:
        data ((iterable of) :py:class:`EvalData`): results to animate
        title (basestring): window title
        refresh_time (int): time in msec to refresh the window must be greater than zero
        replay_gain (float): values above 1 acc- and below 1 decelerate the playback process, must be greater than zero
        save_pics (bool):
        labels: ??

    Return:
    """

    _res_path = "animation_output"

    def __init__(self, data, title="", refresh_time=40, replay_gain=1, save_pics=False, create_video=False,
                 labels=None):
        PgDataPlot.__init__(self, data)

        self.time_data = [np.atleast_1d(data_set.input_data[0]) for data_set in self._data]
        self.spatial_data = [np.atleast_1d(data_set.input_data[1]) for data_set in self._data]
        self.state_data = [data_set.output_data for data_set in self._data]

        self._time_stamp = time.strftime("%H:%M:%S")

        self._pw = pg.plot(title="-".join([self._time_stamp, title, "at", str(replay_gain)]), labels=labels)
        self._pw.addLegend()
        self._pw.showGrid(x=True, y=True, alpha=0.5)

        max_times = [max(data) for data in self.time_data]
        self._endtime = max(max_times)
        self._longest_idx = max_times.index(self._endtime)

        assert refresh_time > 0
        self._tr = refresh_time
        assert replay_gain > 0
        self._t_step = self._tr / 1000 * replay_gain

        spat_min = np.min([np.min(data) for data in self.spatial_data])
        spat_max = np.max([np.max(data) for data in self.spatial_data])
        self._pw.setXRange(spat_min, spat_max)

        state_min = np.min([np.min(data) for data in self.state_data])
        state_max = np.max([np.max(data) for data in self.state_data])
        self._pw.setYRange(state_min, state_max)

        self.save_pics = save_pics
        self.create_video = create_video and save_pics
        self._export_complete = False
        self._exported_files = []

        if self.save_pics:
            self._exporter = pg.exporters.ImageExporter(self._pw.plotItem)
            self._exporter.parameters()['width'] = 1e3

            picture_path = create_dir(self._res_path)
            export_digits = int(np.abs(np.round(np.log10(self._endtime // self._t_step), 0)))
            # ffmpeg uses c-style format strings
            ff_name = "_".join(
                [title.replace(" ", "_"), self._time_stamp.replace(":", "_"), "%0{}d".format(export_digits), ".png"])
            file_name = "_".join(
                [title.replace(" ", "_"), self._time_stamp.replace(":", "_"), "{" + ":0{}d".format(export_digits) + "}",
                 ".png"])
            self._ff_mask = os.sep.join([picture_path, ff_name])
            self._file_mask = os.sep.join([picture_path, file_name])
            self._file_name_counter = 0

        self._time_text = pg.TextItem('t= 0')
        self._pw.addItem(self._time_text)
        self._time_text.setPos(.9 * spat_max, .9 * state_min)

        self._plot_data_items = []
        self._plot_indexes = []
        cls = create_colormap(len(self._data))
        for idx, data_set in enumerate(self._data):
            self._plot_indexes.append(0)
            self._plot_data_items.append(pg.PlotDataItem(pen=pg.mkPen(cls[idx], width=2), name=data_set.name))
            self._pw.addItem(self._plot_data_items[-1])

        self._curr_frame = 0
        self._t = 0

        self._timer = pg.QtCore.QTimer(self)
        self._timer.timeout.connect(self._update_plot)
        self._timer.start(self._tr)

    def _update_plot(self):
        """
        Update plot window.
        """
        new_indexes = []
        for idx, data_set in enumerate(self._data):
            # find nearest time index (0th order interpolation)
            t_idx = (np.abs(self.time_data[idx] - self._t)).argmin()
            new_indexes.append(t_idx)

            # TODO draw grey line if value is outdated

            # update data
            self._plot_data_items[idx].setData(x=self.spatial_data[idx], y=self.state_data[idx][t_idx])

        self._time_text.setText('t= {0:.2f}'.format(self._t))
        self._t += self._t_step
        self._pw.win.setWindowTitle('t= {0:.2f}'.format(self._t))

        if self._t > self._endtime:
            self._t = 0
            if self.save_pics:
                self._export_complete = True
                print("saved pictures using mask: " + self._ff_mask)
                if self.create_video:
                    create_animation(input_file_mask=self._ff_mask)

        if self.save_pics and not self._export_complete:
            if new_indexes != self._plot_indexes:
                # only export a snapshot if the data changed
                f_name = self._file_mask.format(self._file_name_counter)
                self._exporter.export(f_name)
                self._exported_files.append(f_name)
                self._file_name_counter += 1

        self._plot_indexes = new_indexes

    @property
    def exported_files(self):
        if self._export_complete:
            return self._exported_files
        else:
            return None


class PgAdvancedViewWidget(gl.GLViewWidget):
    """
    OpenGL Widget that depends on GLViewWidget and completes it with text labels for the x, y and z axis
    """

    def __init__(self):
        super(PgAdvancedViewWidget, self).__init__()
        self.xlabel = 'x'
        self.posXLabel = [1, 0, 0]
        self.ylabel = 'y'
        self.posYLabel = [0, 1, 0]
        self.zlabel = 'z'
        self.posZLabel = [0, 0, 1]

    def setXLabel(self, text, pos):
        """
        Sets x label on position

        Args:
            test (str): x axis text to render
            pos (list): position as list with [x, y, z] coordinate
        """
        self.xlabel = text
        self.posXLabel = pos
        self.update()

    def setYLabel(self, text, pos):
        """
        Sets y label on position

        Args:
            test (str): y axis text to render
            pos (list): position as list with [x, y, z] coordinate
        """
        self.ylabel = text
        self.posYLabel = pos
        self.update()

    def setZLabel(self, text, pos):
        """
        Sets z label on position

        Args:
            test (str): z axis text to render
            pos (list): position as list with [x, y, z] coordinate
        """
        self.zlabel = text
        self.posZLabel = pos
        self.update()

    def paintGL(self, *args, **kwds):
        """
        Overrides painGL function to render the text labels
        """
        gl.GLViewWidget.paintGL(self, *args, **kwds)
        self.renderText(self.posXLabel[0],
                        self.posXLabel[1],
                        self.posXLabel[2],
                        self.xlabel)
        self.renderText(self.posYLabel[0],
                        self.posYLabel[1],
                        self.posYLabel[2],
                        self.ylabel)
        self.renderText(self.posZLabel[0],
                        self.posZLabel[1],
                        self.posZLabel[2],
                        self.zlabel)


class PgColorBarWidget(pg.GraphicsLayoutWidget):
    """
    OpenGL Widget that depends on GraphicsLayoutWidget and realizes an axis and a color bar
    """

    def __init__(self):
        super(PgColorBarWidget, self).__init__()

        _min = 0
        _max = 1

        # values axis
        self.ax = pg.AxisItem('left')
        self.ax.setRange(_min, _max)
        self.addItem(self.ax)
        # color bar gradients
        cmap = cm.get_cmap(color_map)
        self.gw = PgGradientWidget(cmap=cmap)
        self.setCBRange(_min, _max)
        self.addItem(self.gw)

    def setCBRange(self, _min, _max):
        """
        Sets the minimal and maximal value of axis and color bar

        Args:
            _min (float): minimal value
            _max (float): maximal value
        """
        self.gw.setRange(_min, _max)
        self.ax.setRange(_min, _max)


class PgGradientWidget(pg.GraphicsWidget):
    """
    OpenGL Widget that depends on GraphicsWidget and realizes a color bar that depends on a QGraphicsRectItem and
    QLinearGradient

    Args:
        cmap (matplotlib.cm.Colormap): color map, if None viridis is used
    """

    def __init__(self, cmap=None):
        pg.GraphicsWidget.__init__(self)
        self.length = 100
        self.maxDim = 20
        self.steps = 11
        self.rectSize = 15
        self._min = 0
        self._max = 1

        if cmap is None:
            self.cmap = cm.get_cmap('viridis')
        else:
            self.cmap = cmap

        self.gradRect = pg.QtGui.QGraphicsRectItem(pg.QtCore.QRectF(0, 0, self.length, self.rectSize))
        self.gradRect.setParentItem(self)

        self.setMaxDim(self.rectSize)
        self.resetTransform()
        transform = pg.QtGui.QTransform()
        transform.rotate(270)
        transform.translate(-self.height(), 0)
        self.setTransform(transform)
        self.translate(0, self.rectSize)

        self.updateGradient()

    def resizeEvent(self, ev):
        wlen = max(40, self.height())
        self.setLength(wlen)
        self.setMaxDim(self.rectSize)
        self.resetTransform()
        transform = pg.QtGui.QTransform()
        transform.rotate(270)
        transform.translate(-self.height(), 0)
        self.setTransform(transform)
        self.translate(0, self.rectSize)

    def setMaxDim(self, mx=None):
        """
        Sets the maximal width of the color bar widget

        Args:
             mx (float or None): new width of the color bar widget
        """
        if mx is None:
            mx = self.maxDim
        else:
            self.maxDim = mx

        self.setFixedWidth(mx)
        self.setMaximumHeight(2 ** 32)

    def setLength(self, newLen):
        """
        Gets the new length if the window is resize, updates the size and color of QGraphicsRectItem

        Args:
             newLen: new length of the window
        """
        self.length = float(newLen)
        self.gradRect.setRect(1, -self.rectSize, newLen, self.rectSize)
        self.updateGradient()

    def updateGradient(self):
        """
        Updates QGraphicsRectItem color with the gradient
        """
        self.gradRect.setBrush(pg.QtGui.QBrush(self.getGradient()))

    def getGradient(self):
        """
        Calculates for minimal and maximal value the linear gradient and assigns colors to the gradient.

        Return:
            pg.QtGui.QLinearGradient: linear gradient for current min and max values
        """
        norm = mpl.colors.Normalize(vmin=self._min, vmax=self._max)
        m = cm.ScalarMappable(norm=norm, cmap=self.cmap)

        g = pg.QtGui.QLinearGradient(pg.QtCore.QPointF(0, 0), pg.QtCore.QPointF(self.length, 0))

        t = np.linspace(0, 1, self.steps)
        steps = np.linspace(self._min, self._max, self.steps)
        stops = []
        for idx in range(len(t)):
            _r, _g, _b, _a = m.to_rgba(steps[idx], bytes=True)
            qcol = pg.QtGui.QColor(_r, _g, _b, _a)
            stops.append(tuple([t[idx], qcol]))

        g.setStops(stops)

        return g

    def setRange(self, _min, _max):
        """
        Method updates the min and max value of the colar bar and calculates the new gradient trend

        Args:
            _min (float): set the minimal value of the color bar
            _max (float): set the maximal value of the color bar
        """
        self._min = _min
        self._max = _max
        self.updateGradient()


class PgSurfacePlot(PgDataPlot):
    """
    Plot 3 dimensional data as a surface using OpenGl.

    Args:
        data (:py:class:`pyinduct.core.EvalData`): Data to display, if the the input-vector
            has length of 2, a 3d surface is plotted, if has length 3, this
            surface is animated. Hereby, the time axis is assumed to be the
            first entry of the input vector.
        scales (tuple): Factors to scale the displayed data, each entry
            corresponds to an axis in the input vector with one additional scale
            for the *output_data*. It therefore must be of the size:
            `len(input_data) + 1` . If no scale is given, all axis are scaled
            uniformly.
        animation_axis (int): Index of the axis to use for animation.
            Not implemented, yet and therefore defaults to 0 by now.
        title (str): Window title to display.
        zlabel (str): label for the z axis, default value: x(z,t)
    Todo:
        py attention to animation axis.

    Note:
        For animation this object spawns a `QTimer` which needs an running
        event loop. Therefore remember to store a reference to this object.
    """

    def __init__(self, data, scales=None, animation_axis=0, title="", zlabel='x(z,t)'):
        """

        :type data: object
        """
        PgDataPlot.__init__(self, data)

        layout = pg.QtGui.QGridLayout()

        self.gl_widget = PgAdvancedViewWidget()
        self.gl_widget.setWindowTitle(time.strftime("%H:%M:%S") + ' - ' + title)
        self.gl_widget.setCameraPosition(distance=3, azimuth=-135)
        self.cmap = cm.get_cmap(color_map)

        self.cb = PgColorBarWidget()
        windowHeight = 800
        windowWidth = 800
        colorbarWidth = 60

        # it's basically
        self.gl_widget.setSizePolicy(self.cb.sizePolicy())
        # add 3D widget to the left (first column)
        layout.addWidget(self.gl_widget, 0, 0)
        # add colorbar to the right (second column)
        layout.addWidget(self.cb, 0, 1)
        # Do not allow 2nd column (colorbar) to stretch
        layout.setColumnStretch(1, 0)
        # minimal size of the colorbar
        layout.setColumnMinimumWidth(1, colorbarWidth)
        # Allow 1st column (3D widget) to stretch
        layout.setColumnStretch(0, 1)
        # horizontal size set to be large to prompt colormap to a minimum size
        self.gl_widget.sizeHint = lambda: pg.QtCore.QSize(2 * windowWidth, windowHeight)
        self.cb.sizeHint = lambda: pg.QtCore.QSize(colorbarWidth, windowHeight)
        # this is to remove empty space between
        layout.setHorizontalSpacing(0)
        # set initial size of the window
        self.w = pg.QtGui.QWidget()
        self.w.resize(windowWidth, windowHeight)
        self.w.setLayout(layout)
        self.w.show()
        self.gl_widget.setCameraPosition(distance=3, azimuth=-135)
        self.gl_widget.show()

        self.grid_size = 20

        # calculate minima and maxima
        extrema_list = []
        for data_set in self._data:
            _extrema_list = []
            for entry in data_set.input_data:
                _min_max = [min(entry), max(entry)]
                _extrema_list.append(_min_max)

            extrema_list.append(_extrema_list)

        extrema_arr = np.array(extrema_list)

        extrema = [np.min(extrema_arr[..., 0], axis=0),
                   np.max(extrema_arr[..., 1], axis=0)]

        extrema = np.hstack((
            extrema,
            ([min([data_set.min for data_set in self._data])],
             [max([data_set.max for data_set in self._data])])))

        deltas = np.diff(extrema, axis=0).squeeze()

        # print("minima: {}".format(extrema[0]))
        # print("maxima: {}".format(extrema[1]))
        # print("deltas: {}".format(deltas))

        if scales is None:
            # scale all axes uniformly if no scales are given
            _scales = []
            for value in deltas:
                if np.isclose(value, 0):
                    _scales.append(1)
                else:
                    _scales.append(1 / value)
            self.scales = np.array(_scales)
        else:
            self.scales = scales

        # print(self.scales)
        sc_deltas = deltas * self.scales

        self.plot_items = []
        for idx, data_set in enumerate(self._data):
            if len(data_set.input_data) == 3:
                raise NotImplementedError

                # 2d system over time -> animate
                # assume that for 4d data, the first axis is the time
                self.scales = np.delete(self.scales, animation_axis)
                self.index_offset = 1

                norm = mpl.colors.Normalize(vmin=extrema[0, -1], vmax=extrema[1, -1])
                m = cm.ScalarMappable(norm=norm, cmap=self.cmap)
                colors = m.to_rgba(self._data[idx].output_data)

                plot_item = gl.GLSurfacePlotItem(
                    x=self.scales[1] * np.atleast_1d(data_set.input_data[1]),
                    y=self.scales[2] * np.flipud(
                        np.atleast_1d(data_set.input_data[2])),
                    z=self.scales[3] * data_set.output_data[0],
                    colors=colors,
                    computeNormals=False)
            else:
                # 1d system over time -> static
                self.index_offset = 0

                norm = mpl.colors.Normalize(vmin=extrema[0, -1], vmax=extrema[1, -1])
                m = cm.ScalarMappable(norm=norm, cmap=self.cmap)
                colors = m.to_rgba(self._data[idx].output_data)

                plot_item = gl.GLSurfacePlotItem(
                    x=self.scales[0] * np.atleast_1d(
                        self._data[idx].input_data[0]),
                    y=self.scales[1] * np.flipud(np.atleast_1d(
                        self._data[idx].input_data[1])),
                    z=self.scales[2] * self._data[idx].output_data,
                    colors=colors,
                    computeNormals=False)

            self.gl_widget.addItem(plot_item)
            self.plot_items.append(plot_item)

        if self.index_offset == 1:
            self.t_idx = 0
            self._timer = pg.QtCore.QTimer(self)
            self._timer.timeout.connect(self._update_plot)
            self._timer.start(100)

        self._xygrid = gl.GLGridItem(size=pg.QtGui.QVector3D(1, 1, 1))
        self._xygrid.setSpacing(sc_deltas[0] / 10, sc_deltas[1] / 10, 0)
        self._xygrid.setSize(1.2 * sc_deltas[0], 1.2 * sc_deltas[1], 1)
        self._xygrid.translate(
            .5 * (extrema[1][0] + extrema[0][0]) * self.scales[0],
            .5 * (extrema[1][1] + extrema[0][1]) * self.scales[1],
            extrema[0][2] * self.scales[2] - 0.1 * sc_deltas[0]
        )
        self.gl_widget.addItem(self._xygrid)

        self._xzgrid = gl.GLGridItem(size=pg.QtGui.QVector3D(1, 1, 1))
        self._xzgrid.setSpacing(sc_deltas[0] / 10, sc_deltas[2] / 10, 0)
        self._xzgrid.setSize(1.2 * sc_deltas[0], 1.2 * sc_deltas[2], 1)
        self._xzgrid.rotate(90, 1, 0, 0)
        self._xzgrid.translate(
            .5 * (extrema[1][0] + extrema[0][0]) * self.scales[0],
            extrema[0][1] * self.scales[1] + 1.1 * sc_deltas[0],
            .5 * (extrema[1][2] + extrema[0][2]) * self.scales[2]
        )
        self.gl_widget.addItem(self._xzgrid)

        self._yzgrid = gl.GLGridItem(size=pg.QtGui.QVector3D(1, 1, 1))
        self._yzgrid.setSpacing(sc_deltas[1] / 10, sc_deltas[2] / 10, 0)
        self._yzgrid.setSize(1.2 * sc_deltas[1], 1.2 * sc_deltas[2], 1)
        self._yzgrid.rotate(90, 1, 0, 0)
        self._yzgrid.rotate(90, 0, 0, 1)
        self._yzgrid.translate(
            extrema[0][0] * self.scales[0] + 1.1 * sc_deltas[0],
            .5 * (extrema[1][1] + extrema[0][1]) * self.scales[1],
            .5 * (extrema[1][2] + extrema[0][2]) * self.scales[2]
        )
        self.gl_widget.addItem(self._yzgrid)

        self.gl_widget.setXLabel('t', pos=[
            extrema[0][0] * self.scales[0] + sc_deltas[0] - self.scales[0] * extrema[1][0],
            extrema[0][1] * self.scales[1] + 0.35 * sc_deltas[1] - self.scales[1] * extrema[1][1],
            extrema[0][2] * self.scales[2] + 0.4 * sc_deltas[2] - self.scales[2] * extrema[1][2]])
        self.gl_widget.setYLabel('z', pos=[
            extrema[0][0] * self.scales[0] + 0.35 * sc_deltas[0] - self.scales[0] * extrema[1][0],
            extrema[0][1] * self.scales[1] + sc_deltas[1] - self.scales[1] * extrema[1][1],
            extrema[0][2] * self.scales[2] + 0.4 * sc_deltas[2] - self.scales[2] * extrema[1][2]])
        self.gl_widget.setZLabel(zlabel, pos=[
            extrema[0][0] * self.scales[0] + 1.6 * sc_deltas[0] - self.scales[0] * extrema[1][0],
            extrema[0][1] * self.scales[1] + 1.6 * sc_deltas[1] - self.scales[1] * extrema[1][1],
            extrema[0][2] * self.scales[2] + 1.6 * sc_deltas[2] - self.scales[2] * extrema[1][2]])
        self.cb.setCBRange(extrema[0, -1], extrema[1, -1])

        # set origin (zoom point) to the middle of the figure
        # (a better way would be to realize it directly via a method of
        # self.gl_widget, instead to shift all items)
        [item.translate(-self.scales[0] * extrema[1][0] + sc_deltas[0] / 2,
                        -self.scales[1] * extrema[1][1] + sc_deltas[1] / 2,
                        -self.scales[2] * extrema[1][2] + sc_deltas[2] / 2)
         for item in self.gl_widget.items]

    def _update_plot(self):
        """
        Update the rendering
        """
        for idx, item in enumerate(self.plot_items):
            x_data = self.scales[1] * np.atleast_1d(self._data[idx].input_data[1])
            y_data = self.scales[2] * np.flipud(
                np.atleast_1d(self._data[idx].input_data[2]))
            z_data = self.scales[3] * self._data[idx].output_data[self.t_idx]
            item.setData(x=x_data, y=y_data, z=z_data)

        self.t_idx += 1

        # TODO check if every array has enough timestamps in it
        if self.t_idx >= len(self._data[0].input_data[0]):
            self.t_idx = 0


# TODO: alpha
class PgSlicePlot(PgDataPlot):
    """
    Plot selected slice of given DataSets.
    """

    # TODO think about a nice slice strategy see pyqtgraph for inspiration
    def __init__(self, data, title=None):
        PgDataPlot.__init__(self, data)
        self.dim = self._data[0].output_data.shape

        self.win = pg.QtGui.QMainWindow()
        self.win.resize(800, 800)
        self.win.setWindowTitle("PgSlicePlot: {}".format(title))
        self.cw = pg.QtGui.QWidget()
        self.win.setCentralWidget(self.cw)
        self.l = pg.QtGui.QGridLayout()
        self.cw.setLayout(self.l)
        self.image_view = pg.ImageView(name="img_view")
        self.l.addWidget(self.image_view, 0, 0)
        self.slice_view = pg.PlotWidget(name="slice")
        self.l.addWidget(self.slice_view)
        self.win.show()

        # self.imv2 = pg.ImageView()
        # self.l.addWidget(self.imv2, 1, 0)

        self.roi = pg.LineSegmentROI([[0, self.dim[1] - 1], [self.dim[0] - 1, self.dim[1] - 1]], pen='r')
        self.image_view.addItem(self.roi)
        self.image_view.setImage(self._data[0].output_data)
        #
        # self.plot_window.showGrid(x=True, y=True, alpha=.5)
        # self.plot_window.addLegend()
        #
        # input_idx = 0 if self.data_slice.shape[0] > self.data_slice.shape[1] else 0
        # for data_set in data:
        #     self.plot_window.plot(data_set.input_data[input_idx], data_set.output_data[self.data_slice],
        #                           name=data.name)


class PgLinePlot2d(PgDataPlot):
    """
    Plots a list of 1D :py:class:`EvalData` objects as a OpenGL line plot

    Args:
        data (list(:py:class:`EvalData`)): list of objects to plot
        title (str): title string
    """

    def __init__(self, data, title=''):
        PgDataPlot.__init__(self, data)

        self.xData = [np.atleast_1d(data_set.input_data[0]) for data_set in self._data]
        self.yData = [data_set.output_data for data_set in self._data]

        self._pw = pg.plot(title=title)
        self._pw.addLegend()
        self._pw.showGrid(x=True, y=True, alpha=0.5)

        xData_min = np.nanmin([np.nanmin(data) for data in self.xData])
        xData_max = np.nanmax([np.nanmax(data) for data in self.xData])
        self._pw.setXRange(xData_min, xData_max)

        yData_min = np.nanmin([np.nanmin(data) for data in self.yData])
        yData_max = np.nanmax([np.nanmax(data) for data in self.yData])
        self._pw.setYRange(yData_min, yData_max)

        self._plot_data_items = []
        self._plot_indexes = []
        cls = create_colormap(len(self._data))
        for idx, data_set in enumerate(self._data):
            self._plot_indexes.append(0)
            self._plot_data_items.append(pg.PlotDataItem(pen=pg.mkPen(cls[idx], width=2), name=data_set.name))
            self._pw.addItem(self._plot_data_items[-1])
            self._plot_data_items[idx].setData(x=self.xData[idx], y=self.yData[idx])


# TODO: alpha
class PgLinePlot3d(PgDataPlot):
    """
    Ulots a series of n-lines of the systems state.
    Scaling in z-direction can be changed with the scale setting.
    """

    def __init__(self, data, n=50, scale=1):
        PgDataPlot.__init__(self, data)

        self.w = gl.GLViewWidget()
        self.w.opts['distance'] = 40
        self.w.show()
        self.w.setWindowTitle(data[0].name)

        # grids
        gx = gl.GLGridItem()
        gx.rotate(90, 0, 1, 0)
        gx.translate(-10, 0, 0)
        self.w.addItem(gx)
        gy = gl.GLGridItem()
        gy.rotate(90, 1, 0, 0)
        gy.translate(0, -10, 0)
        self.w.addItem(gy)
        gz = gl.GLGridItem()
        gz.translate(0, 0, -10)
        self.w.addItem(gz)

        res = self._data[0]
        z_vals = res.input_data[1][::-1] * scale

        t_subsets = np.linspace(0, np.array(res.input_data[0]).size, n, endpoint=False, dtype=int)

        for t_idx, t_val in enumerate(t_subsets):
            t_vals = np.array([res.input_data[0][t_val]] * len(z_vals))
            pts = np.vstack([t_vals, z_vals, res.output_data[t_val, :]]).transpose()
            plt = gl.GLLinePlotItem(pos=pts, color=pg.glColor((t_idx, n * 1.3)),  # width=(t_idx + 1) / 10.,
                                    width=2, antialias=True)
            self.w.addItem(plt)


class MplSurfacePlot(DataPlot):
    """
    Plot as 3d surface.
    """

    def __init__(self, data, keep_aspect=False, fig_size=(12, 8), zlabel='$\quad x(z,t)$'):
        DataPlot.__init__(self, data)

        for i in range(len(self._data)):

            # data
            x = self._data[i].input_data[1]
            y = self._data[i].input_data[0]
            z = self._data[i].output_data
            xx, yy = np.meshgrid(x, y)

            # figure
            fig = plt.figure(figsize=fig_size, facecolor='white')
            ax = fig.gca(projection='3d')
            if keep_aspect:
                ax.set_aspect('equal', 'box')
            ax.w_xaxis.set_pane_color((1, 1, 1, 1))
            ax.w_yaxis.set_pane_color((1, 1, 1, 1))
            ax.w_zaxis.set_pane_color((1, 1, 1, 1))

            # labels
            ax.set_ylabel('$t$')
            ax.set_xlabel('$z$')
            ax.zaxis.set_rotate_label(False)
            ax.set_zlabel(zlabel, rotation=0)

            cmap = plt.get_cmap(color_map)

            ax.plot_surface(xx, yy, z, rstride=2, cstride=2, cmap=cmap, antialiased=False)


class MplSlicePlot(PgDataPlot):
    """
    Get list (eval_data_list) of ut.EvalData objects and plot the temporal/spatial slice, by spatial_point/time_point,
    from each ut.EvalData object, in one plot.
    For now: only ut.EvalData objects with len(input_data) == 2 supported
    """

    def __init__(self, eval_data_list, time_point=None, spatial_point=None, ylabel="", legend_label=None,
                 legend_location=1, figure_size=(10, 6)):

        if not ((isinstance(time_point, Number) ^ isinstance(spatial_point, Number)) and (
                    isinstance(time_point, type(None)) ^ isinstance(spatial_point, type(None)))):
            raise TypeError("Only one kwarg *_point can be passed,"
                            "which has to be an instance from type numbers.Number")

        DataPlot.__init__(self, eval_data_list)

        plt.figure(facecolor='white', figsize=figure_size)
        plt.ylabel(ylabel)
        plt.grid(True)

        # TODO: move to ut.EvalData
        len_data = len(self._data)
        interp_funcs = [si.interp2d(eval_data.input_data[1], eval_data.input_data[0], eval_data.output_data) for
                        eval_data in eval_data_list]

        if time_point is None:
            slice_input = [data_set.input_data[0] for data_set in self._data]
            slice_data = [interp_funcs[i](spatial_point, slice_input[i]) for i in range(len_data)]
            plt.xlabel('$t$')
        elif spatial_point is None:
            slice_input = [data_set.input_data[1] for data_set in self._data]
            slice_data = [interp_funcs[i](slice_input[i], time_point) for i in range(len_data)]
            plt.xlabel('$z$')
        else:
            raise TypeError

        if legend_label is None:
            show_leg = False
            legend_label = [evald.name for evald in eval_data_list]
        else:
            show_leg = True

        for i in range(0, len_data):
            plt.plot(slice_input[i], slice_data[i], label=legend_label[i])

        if show_leg:
            plt.legend(loc=legend_location)


def mpl_activate_latex():
    """
    Activate full (label, ticks, ...) latex printing in matplotlib plots.
    """
    plt.rcParams['text.latex.preamble'] = [r"\usepackage{lmodern}",
                                           r"\usepackage{chemformula}"]
    params = {'text.usetex': True, 'font.size': 15, 'font.family': 'lmodern', 'text.latex.unicode': True, }
    plt.rcParams.update(params)


def mpl_3d_remove_margins():
    """
    Remove thin margins in matplotlib 3d plots.
    The Solution is from `Stackoverflow`_.

    .. _Stackoverflow:
        http://stackoverflow.com/questions/16488182/
    """

    from mpl_toolkits.mplot3d.axis3d import Axis

    if not hasattr(Axis, "_get_coord_info_old"):
        def _get_coord_info_new(self, renderer):
            mins, maxs, centers, deltas, tc, highs = self._get_coord_info_old(renderer)
            mins += deltas / 4
            maxs -= deltas / 4
            return mins, maxs, centers, deltas, tc, highs

        Axis._get_coord_info_old = Axis._get_coord_info
        Axis._get_coord_info = _get_coord_info_new


def save_2d_pg_plot(plot, filename):
    """
    Save a given pyqtgraph plot in the folder <current path>.pictures_plot
    under the given filename :py:obj:`filename`.

    Args:
        plot (:py:class:`pyqtgraph.plotItem`): Pyqtgraph plot.
        filename (str): Png picture filename.

    Return:
        tuple of 2 str's: Path with filename and path only.
    """

    path = create_dir('pictures_plot') + os.path.sep
    path_filename = path + filename + '.png'
    exporter = pg.exporters.ImageExporter(plot.plotItem)
    exporter.parameters()['width'] = 1e3
    exporter.export(path_filename)
    return path_filename, path


def visualize_roots(roots, grid, function, cmplx=False):
    """
    Visualize a given set of roots by examining the output
    of the generating function.

    Args:
        roots (array like): list of roots to display.
        grid (list): list of arrays that form the grid, used for
            the evaluation of the given *function*
        function (callable): possibly vectorial function handle
            that will take input of of the shape ('len(grid)', )
        cmplx (bool): If True, the complex valued *function* is
            handled as a vectorial function returning [Re(), Im()]
    """
    if isinstance(grid[0], Number):
        grid = [grid]

    dim = len(grid)
    assert dim < 3

    if cmplx:
        assert dim == 2
        function = complex_wrapper(function)
        roots = np.array([np.real(roots), np.imag(roots)]).T

    grids = np.meshgrid(*[row for row in grid])
    values = np.vstack([arr.flatten() for arr in grids]).T

    components = []
    absolute = []
    for val in values:
        components.append(function(val))
        absolute.append(np.linalg.norm(components[-1]))

    comp_values = np.array(components)
    abs_values = np.array(absolute)

    # plot roots
    pg.mkQApp()
    pw = pg.GraphicsLayoutWidget()
    pw.setWindowTitle("Root Visualization")

    if dim == 1:
        # plot function with roots
        pl = pw.addPlot()
        pl.plot(roots, np.zeros(roots.shape[0]), pen=None, symbolPen=pg.mkPen("g"))
        pl.plot(np.squeeze(values), np.squeeze(comp_values), pen=pg.mkPen("b"))
    else:
        # plot function components
        rect = pg.QtCore.QRectF(grid[0][0],
                                grid[1][0],
                                grid[0][-1] - grid[0][0],
                                grid[1][-1] - grid[1][0])
        for idx in range(comp_values.shape[1]):
            lbl = pg.LabelItem(text="Component {}".format(idx),
                               angle=-90,
                               bold=True,
                               size="10pt")
            pw.addItem(lbl)

            p_img = pw.addPlot()
            img = pg.ImageItem()
            img.setImage(comp_values[:, idx].reshape(grids[0].shape).T)
            img.setRect(rect)
            p_img.addItem(img)

            # add roots on top
            p_img.plot(roots[:, 0], roots[:, 1],
                       pen=None,
                       symbolPen=pg.mkPen("g"))

            hist = pg.HistogramLUTItem()
            hist.setImageItem(img)
            pw.addItem(hist)

            pw.nextRow()

        # plot absolute value of function
        lbl = pg.LabelItem(text="Absolute Value",
                           angle=-90,
                           bold=True,
                           size="10pt")
        pw.addItem(lbl)
        p_abs = pw.addPlot()
        img = pg.ImageItem()
        img.setImage(abs_values.reshape(grids[0].shape).T)
        img.setRect(rect)
        p_abs.addItem(img)

        hist = pg.HistogramLUTItem()
        hist.setImageItem(img)
        pw.addItem(hist)
        # add roots on top
        p_abs.plot(roots[:, 0], roots[:, 1], pen=None, symbolPen=pg.mkPen("g"))

    pw.show()
    pg.QAPP.exec_()
