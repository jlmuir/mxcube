#
#  Project: MXCuBE
#  https://github.com/mxcube.
#
#  This file is part of MXCuBE software.
#
#  MXCuBE is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  MXCuBE is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with MXCuBE.  If not, see <http://www.gnu.org/licenses/>.
#
#  Please user PEP 0008 -- "Style Guide for Python Code" to format code
#  https://www.python.org/dev/peps/pep-0008/
import os

import logging
import gevent
import jsonpickle
from datetime import datetime
from collections import namedtuple

from PyQt4 import QtCore
from PyQt4 import QtGui
from PyQt4 import uic

import Qt4_queue_item
import queue_entry
import queue_model_objects_v1 as queue_model_objects

from BlissFramework import Qt4_Icons
from BlissFramework.Utils import Qt4_widget_colors
from widgets.Qt4_confirm_dialog import ConfirmDialog
from widgets.Qt4_plate_navigator_widget import PlateNavigatorWidget
from queue_model_enumerables_v1 import CENTRING_METHOD

SCFilterOptions = namedtuple('SCFilterOptions', 
                             ['FREE_PIN',
                              'SAMPLE_CHANGER', 
                              'PLATE', 
                              'MOUNTED_SAMPLE']) 

SC_FILTER_OPTIONS = SCFilterOptions(0, 1, 2, 3)


class DataCollectTree(QtGui.QWidget):
    """
    Descript. :
    """ 

    def __init__(self, parent = None, name = "data_collect", 
                 selection_changed = None):
        """
        Descript. :
        """
 
        QtGui.QWidget.__init__(self, parent)

        self.setObjectName(name)

        # Hardware objects ----------------------------------------------------
        self.queue_hwobj = None
        self.queue_model_hwobj = None
        self.beamline_setup_hwobj = None

        # Internal values -----------------------------------------------------
        self.enable_collect_condition = None
        self.collecting = False
        self.sample_mount_method = 0
        self.centring_method = 0
        self.sample_centring_result = gevent.event.AsyncResult()
        self.tree_brick = self.parent()
        self.sample_item_list = []
        self.collect_tree_task = None
        self.user_stopped = False
        self.last_added_item = None
        self.item_copy = None
        
        self.selection_changed_cb = None
        self.collect_stop_cb = None
        #self.clear_centred_positions_cb = None
        self.run_cb = None
        self.item_menu = None

        # Signals ------------------------------------------------------------

        # Slots ---------------------------------------------------------------

        # Graphic elements ----------------------------------------------------
        self.confirm_dialog = ConfirmDialog(self, 'Confirm Dialog')
        self.confirm_dialog.setModal(True)

        self.pin_icon = Qt4_Icons.load_icon("sample_axis.png")
        self.task_icon = Qt4_Icons.load_icon("task.png")
        self.play_icon = Qt4_Icons.load_icon("VCRPlay.png")
        self.stop_icon = Qt4_Icons.load_icon("Stop.png")
        self.ispyb_icon = Qt4_Icons.load_icon("SampleChanger2.png")
        self.caution_icon = Qt4_Icons.load_icon("Caution2.png")
        
        self.button_widget = QtGui.QWidget(self)                
        self.up_button = QtGui.QPushButton(self.button_widget)
        self.up_button.setIcon(Qt4_Icons.load_icon("Up2.png"))
        self.up_button.setFixedHeight(25)
        self.down_button = QtGui.QPushButton(self.button_widget)
        self.down_button.setIcon(Qt4_Icons.load_icon("Down2.png"))
        self.down_button.setFixedHeight(25)

        self.copy_button = QtGui.QPushButton(self.button_widget)
        self.copy_button.setIcon(Qt4_Icons.load_icon("copy.png"))
        self.copy_button.setDisabled(True)
        self.copy_button.setToolTip("Copy highlighted queue entries")

        self.delete_button = QtGui.QPushButton(self.button_widget)
        self.delete_button.setIcon(Qt4_Icons.load_icon("bin_small.png"))
        self.delete_button.setDisabled(True)
        self.delete_button.setToolTip("Delete highlighted queue entries")

        self.collect_button = QtGui.QPushButton(self.button_widget)
        self.collect_button.setText("Collect Queue")
        self.collect_button.setFixedWidth(125)
        self.collect_button.setIcon(self.play_icon)
        self.collect_button.setDisabled(True)
        Qt4_widget_colors.set_widget_color(self.collect_button, 
                                           Qt4_widget_colors.LIGHT_GREEN,
                                           QtGui.QPalette.Button)

        self.continue_button = QtGui.QPushButton(self.button_widget)
        self.continue_button.setText('Pause')
        self.continue_button.setDisabled(True)
        self.continue_button.setToolTip("Pause after current data collection")

        self.tree_splitter = QtGui.QSplitter(QtCore.Qt.Vertical, self)
        current_widget = QtGui.QWidget(self.tree_splitter)
        current_label = QtGui.QLabel("<b>Current</b>", current_widget)
        current_label.setAlignment(QtCore.Qt.AlignCenter)
        self.sample_tree_widget = QtGui.QTreeWidget(self)

        history_widget = QtGui.QWidget(self.tree_splitter)
        history_widget.hide()
        history_label = QtGui.QLabel("<b>History</b>", history_widget)
        history_label.setAlignment(QtCore.Qt.AlignCenter)
        self.history_tree_widget = QtGui.QTreeWidget(history_widget)
        
        self.plate_navigator_cbox = QtGui.QCheckBox("Plate navigator", self)
        self.plate_navigator_widget = PlateNavigatorWidget(self)
        self.plate_navigator_widget.hide()

        # Layout --------------------------------------------------------------
        button_widget_grid_layout = QtGui.QGridLayout(self.button_widget) 
        button_widget_grid_layout.addWidget(self.up_button, 0, 0)
        button_widget_grid_layout.addWidget(self.down_button, 0, 1)
        button_widget_grid_layout.addWidget(self.collect_button, 1, 0, 1, 2)
        button_widget_grid_layout.addWidget(self.copy_button, 0, 3)
        button_widget_grid_layout.addWidget(self.delete_button, 0, 4)
        button_widget_grid_layout.addWidget(self.continue_button, 1, 3, 1, 2)
        button_widget_grid_layout.setColumnStretch(2, 1)
        button_widget_grid_layout.setContentsMargins(0, 0, 0, 0)
        button_widget_grid_layout.setSpacing(1)

        current_widget_layout = QtGui.QVBoxLayout(current_widget)
        current_widget_layout.addWidget(current_label)
        current_widget_layout.addWidget(self.sample_tree_widget)
        current_widget_layout.setContentsMargins(2, 2, 2, 2)
        current_widget_layout.setSpacing(1)

        history_widget_layout = QtGui.QVBoxLayout(history_widget)
        history_widget_layout.addWidget(history_label)
        history_widget_layout.addWidget(self.history_tree_widget)
        history_widget_layout.setContentsMargins(2, 2, 2, 2)
        history_widget_layout.setSpacing(1)
        
        main_layout = QtGui.QVBoxLayout(self)
        #main_layout.addWidget(self.sample_tree_widget)
        main_layout.addWidget(self.tree_splitter)
        main_layout.addWidget(self.plate_navigator_cbox)
        main_layout.addWidget(self.plate_navigator_widget)
        main_layout.addWidget(self.button_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(1) 

        # SizePolicies --------------------------------------------------------
        #self.sample_tree_widget.setSizePolicy(QtGui.QSizePolicy(
        #     QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding))

        # Qt signal/slot connections ------------------------------------------
        self.up_button.clicked.connect(self.up_click)
        self.down_button.clicked.connect(self.down_click)
        self.copy_button.clicked.connect(self.copy_click)
        self.delete_button.clicked.connect(self.delete_click)
        self.collect_button.clicked.connect(self.collect_stop_toggle)
        self.sample_tree_widget.itemSelectionChanged.\
             connect(self.sample_tree_widget_selection)
        self.sample_tree_widget.contextMenuEvent = self.show_context_menu
        self.sample_tree_widget.itemDoubleClicked.connect(self.item_double_click)
        self.sample_tree_widget.itemClicked.connect(self.item_click)
        self.sample_tree_widget.itemChanged.connect(self.item_changed)

        self.confirm_dialog.continueClickedSignal.connect(self.collect_items)
        self.continue_button.clicked.connect(self.continue_button_click)

        self.history_tree_widget.itemDoubleClicked.connect(self.item_double_click)

        self.plate_navigator_cbox.stateChanged.\
             connect(self.use_plate_navigator)

        # Other ---------------------------------------------------------------    
        self.sample_tree_widget.setColumnCount(3)
        #self.sample_tree_widget.setColumnWidth(0, 150)
        self.sample_tree_widget.setColumnWidth(1, 130)
        self.sample_tree_widget.header().setDefaultSectionSize(280)
        self.sample_tree_widget.header().hide()
        self.sample_tree_widget.setRootIsDecorated(1)
        self.sample_tree_widget.setCurrentItem(self.sample_tree_widget.topLevelItem(0))
        self.sample_tree_widget.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.setAttribute(QtCore.Qt.WA_WState_Polished)      
        self.sample_tree_widget.viewport().installEventFilter(self)

        self.history_tree_widget.setColumnCount(3)
        self.history_tree_widget.setColumnWidth(0, 80)
        self.history_tree_widget.setColumnWidth(1, 50)
        self.history_tree_widget.header().setDefaultSectionSize(80)
        self.history_tree_widget.header().hide()
        self.history_tree_widget.setRootIsDecorated(False)
        #self.sample_tree_widget.setSelectionMode(\
        #     QtGui.QAbstractItemView.MultiSelection)

    def init_plate_navigator(self, plate_navigator_hwobj):
        self.plate_navigator_widget.init_plate_view(plate_navigator_hwobj)

    def eventFilter(self, _object, event):
        """
        Descript. :
        """
        if event.type() == QtCore.QEvent.MouseButtonDblClick:
            self.show_details()
            return True
        else:
            return False

    def enable_collect(self, state):
        """
        Descript. :
        """
        self.sample_tree_widget.setDisabled(not state)
        self.collect_button.setDisabled(not state)
        #self.up_button.setDisabled(not state)
        #self.down_button.setDisabled(not state)
        self.delete_button.setDisabled(not state)

    def show_context_menu(self, context_menu_event):
        """
        Descript. :
        """
        self.item_menu = QtGui.QMenu(self.sample_tree_widget)
        item = self.sample_tree_widget.currentItem()

        if item:
            add_remove = True
            add_details = False
            self.item_menu.addAction("Rename", self.rename_treewidget_item)
            if isinstance(item, Qt4_queue_item.TaskQueueItem):
                if not isinstance(item.get_model(),
                                  queue_model_objects.SampleCentring):
                    self.item_menu.addSeparator()
                    self.item_menu.addAction("Cut", self.cut_item)
                    self.item_menu.addAction("Copy", self.copy_item)
                    paste_action = self.item_menu.addAction("Paste", self.paste_item)
                    paste_action.setEnabled(self.item_copy is not None)
                    self.item_menu.addSeparator()
                    self.item_menu.addAction("Save in file", self.save_item)
                    self.item_menu.addAction("Load from file", self.load_item)
                    add_details = True
                else:
                    self.item_menu.addSeparator()
            elif isinstance(item, Qt4_queue_item.DataCollectionGroupQueueItem):
                self.item_menu.addSeparator()
                paste_action = self.item_menu.addAction("Paste", self.paste_item)
                paste_action.setEnabled(self.item_copy is not None)
                add_details = True
            elif isinstance(item, Qt4_queue_item.SampleQueueItem):
                paste_action = self.item_menu.addAction("Paste", self.paste_item)
                paste_action.setEnabled(self.item_copy is not None)
                self.item_menu.addSeparator()
                if not item.get_model().free_pin_mode:
                    if self.beamline_setup_hwobj.diffractometer_hwobj.in_plate_mode():
                        self.plate_sample_to_mount = item
                        self.item_menu.addAction("Move", self.mount_sample)
                    else:
                        if self.is_mounted_sample_item(item):
                            self.item_menu.addAction("Un-Mount", self.unmount_sample)
                        else:
                            self.item_menu.addAction("Mount", self.mount_sample)
                self.item_menu.addSeparator()
                add_remove = False
                add_details = True
            elif isinstance(item, Qt4_queue_item.BasketQueueItem):
                paste_action = self.item_menu.addAction("Paste", self.paste_item)
                paste_action.setEnabled(self.item_copy is not None)
                self.item_menu.addSeparator()
                add_remove = False
            
            self.item_menu.addAction("Insert from file", self.insert_item)
            self.item_menu.addSeparator()
            if add_remove:
                self.item_menu.addAction("Remove", self.delete_click) 
            if add_details:
                self.item_menu.addAction("Details", self.show_details)
            self.item_menu.popup(QtGui.QCursor.pos())
        
    def item_double_click(self):
        """
        Descript. :
        """
        self.show_details()

    def item_click(self):
        """
        Descript. :
        """
        self.check_for_path_collisions()
        self.sample_tree_widget_selection()
             
    def item_changed(self, item, column):
        """
        Descript. : As there is no signal when item is checked/unchecked
                    it is necessary to update item based on QTreeWidget
                    signal itemChanged. 
                    Item check state is updated when checkbox is toggled
                    (to avoid update when text is changed)                    
        """
        #if item.checkState(0) != item.get_previous_check_state():
        #   item.update_check_state()        

        # IK. This type check should not be here,because all tree items are 
        # anyway QueueItems. but somehow on the init item got native
        # QTreeWidgetItem type and method was not found. Interesting...

        if isinstance(item, Qt4_queue_item.QueueItem):
            item.update_check_state(item.checkState(0))

    def use_plate_navigator(self, state):
        self.plate_navigator_widget.setVisible(state)

    def item_parameters_changed(self):
        items = self.get_selected_items()
        for item in items:
            item.update_display_name()

    def context_collect_item(self):
        """
        Descript. :
        """
        items = self.get_selected_items()
        
        if len(items) == 1:
            item = items[0]
        
            # Turn this item on (check it), incase its not already checked.
            if item.state() == 0:
                item.setOn(True)
            
            self.collect_items(items)

    def show_details(self):
        """
        Descript. :
        """
        items = self.get_selected_items()
        if len(items) == 1:
            item = items[0]
            if isinstance(item, Qt4_queue_item.SampleQueueItem):
                self.tree_brick.show_sample_tab(item)
            elif isinstance(item, Qt4_queue_item.DataCollectionQueueItem):
                data_collection = item.get_model()
                if data_collection.is_mesh():
                    self.tree_brick.show_advanced_tab(item)
                else:
                    self.tree_brick.show_datacollection_tab(item)
            elif isinstance(item, Qt4_queue_item.CharacterisationQueueItem):
                self.tree_brick.show_char_parameters_tab(item)
            elif isinstance(item, Qt4_queue_item.EnergyScanQueueItem):
                self.tree_brick.show_energy_scan_tab(item)
            elif isinstance(item, Qt4_queue_item.XRFSpectrumQueueItem):
                self.tree_brick.show_xrf_spectrum_tab(item)
            elif isinstance(item, Qt4_queue_item.GenericWorkflowQueueItem):
                self.tree_brick.show_workflow_tab(item)
            elif isinstance(item, Qt4_queue_item.DataCollectionGroupQueueItem):
                self.tree_brick.show_dcg_tab(item)
        #elif len(items) == 0:
        #    self.tree_brick.show_sample_tab()

    def rename_treewidget_item(self):
        """
        Descript. :
        """
        items = self.get_selected_items()
        if len(items) == 1:
            items[0].setFlags(QtCore.Qt.ItemIsSelectable |
                              QtCore.Qt.ItemIsEnabled |
                              QtCore.Qt.ItemIsEditable)
            self.sample_tree_widget.editItem(items[0])
            items[0].setFlags(QtCore.Qt.ItemIsSelectable |
                              QtCore.Qt.ItemIsEnabled)
            items[0].get_model().set_name(items[0].text(0))

    def mount_sample(self):
        """
        Descript. :
        """
        self.enable_collect(False)
        gevent.spawn(self.mount_sample_task)

    def mount_sample_task(self):
        """
        Descript. :
        """
        items = self.get_selected_items()
        
        if len(items) == 1:
            if not items[0].get_model().free_pin_mode:
                self.sample_centring_result = gevent.event.AsyncResult()
                try:
                   queue_entry.mount_sample(self.beamline_setup_hwobj,
                        items[0], items[0].get_model(), self.centring_done,
                        self.sample_centring_result)
                except Exception as e:
                    items[0].setText(1, "Error loading")
                    msg = "Error loading sample, please check" +\
                          " sample changer: " + str(e.message)
                    logging.getLogger("GUI").error(msg)
                finally:
                    self.enable_collect(True)
            else:
                logging.getLogger("GUI").\
                  info('Its not possible to mount samples in free pin mode')

    def centring_done(self, success, centring_info):
        """
        Descript. :
        """
        if success:
            self.sample_centring_result.set(centring_info)
        else:
            msg = "Loop centring failed or was cancelled, " +\
                  "please continue manually."
            logging.getLogger("GUI").warning(msg)

    def unmount_sample(self):
        """
        Descript. :
        """
        self.enable_collect(False)
        gevent.spawn(self.unmount_sample_task)

    def unmount_sample_task(self):
        """
        Descript. :
        """
        items = self.get_selected_items()

        if len(items) == 1:
            self.beamline_setup_hwobj.shape_history_hwobj.clear_all()
            logging.getLogger("GUI").\
                info("All centred positions associated with this " + \
                     "sample will be lost.")

            location = items[0].get_model().location

            sample_changer = None
            if self.sample_mount_method == 1:
                try:
                   sample_changer = self.beamline_setup_hwobj.sample_changer_hwobj
                except AttributeError:
                   sample_changer = None
            elif self.sample_mount_method == 2:
                try:
                   sample_changer = self.beamline_setup_hwobj.plate_manipulator_hwobj
                except AttributeError:
                   sample_changer = None

            if sample_changer:
                if hasattr(sample_changer, '__TYPE__')\
                   and sample_changer.__TYPE__ in ('CATS', 'Marvin'):
                    sample_changer.unload(wait=True)
                else:
                    sample_changer.unload(22, sample_location = location, wait = False)

            items[0].setOn(False)
            items[0].set_mounted_style(False)
        self.enable_collect(True)

    def sample_tree_widget_selection(self):
        """
        Descript. :
        """
        items = self.get_selected_items()
        self.copy_button.setDisabled(True)
        self.up_button.setDisabled(True)
        self.down_button.setDisabled(True)         

        for item in items:
            if isinstance(item, Qt4_queue_item.TaskQueueItem):
                self.copy_button.setDisabled(False)
                if len(items) == 1:
                    if item.parent().indexOfChild(item) > 0:
                        self.up_button.setDisabled(False)
                    if item.parent().indexOfChild(item) < item.parent().childCount() - 1:
                        self.down_button.setDisabled(False)
            break

        self.selection_changed_cb(items)        

        checked_items = self.get_checked_items()
        self.collect_button.setEnabled(len(checked_items) > 1 and \
                                       self.enable_collect_condition)

    def add_empty_task_node(self):
        """
        Descript. :
        """
        samples = self.get_selected_samples()
        task_node = queue_model_objects.TaskGroup()
        task_node.set_name('Collection group')
        Qt4_queue_item.DataCollectionGroupQueueItem(samples[0], 
                                                samples[0].lastItem(),
                                                task_node.get_display_name())

    def get_item_by_model(self, parent_node):
        """
        Descript. :
        """
        it = QtGui.QTreeWidgetItemIterator(self.sample_tree_widget)
        item = it.value()
    
        while item:
            if item.get_model() is parent_node:
                return item

            it += 1
            item = it.value()

        return self.sample_tree_widget

    def last_top_level_item(self):
        """
        Descript. :
        """
        last_child_index = self.sample_tree_widget.topLevelItemCount() - 1
        return self.sample_tree_widget.topLevelItem(last_child_index) 

    def add_to_view(self, parent, task):
        """
        Descript. : Adds queue element to the tree. After element has been
                    added selection of tree is cleared. 
                    If entry is a collection then it is selected and 
                    selection callback is raised.
        """
        view_item = None
        parent_tree_item = self.get_item_by_model(parent)

        if parent_tree_item is self.sample_tree_widget:
            last_item = self.last_top_level_item()
        else:
            last_item = parent_tree_item.lastItem()

        cls = Qt4_queue_item.MODEL_VIEW_MAPPINGS[task.__class__]
        view_item = cls(parent_tree_item, last_item, task.get_display_name())

        if isinstance(task, queue_model_objects.Basket):
            view_item.setExpanded(task.get_is_present() == True)
            #view_item.setDisabled(not task.get_is_present())
        else:
            view_item.setExpanded(True)

        self.queue_model_hwobj.view_created(view_item, task)
        self.collect_button.setDisabled(False)

        self.last_added_item = view_item

    def get_selected_items(self):
        """
        Descript. :
        """
        return self.sample_tree_widget.selectedItems()

    def de_select_items(self):
        it = QtGui.QTreeWidgetItemIterator(self.sample_tree_widget)
        item = it.value()

        while item:
            item.setCheckState(0, QtCore.Qt.Unchecked)
            it += 1
            item = it.value()

    def get_selected_samples(self):
        """
        Descript. :
        """
        res_list = []
        for item in self.get_selected_items():
            if isinstance(item,  Qt4_queue_item.SampleQueueItem):
               res_list.append(item)
        return res_list
    
    def get_selected_tasks(self):
        """
        Descript. :
        """
        res_list = []
        for item in self.get_selected_items():
            if isinstance(item,  Qt4_queue_item.TaskQueueItem):
               res_list.append(item)
        return res_list

    def get_selected_dcs(self):
        """
        Descript. :
        """
        res_list = []
        for item in self.get_selected_items():
            if isinstance(item,  Qt4_queue_item.DataCollectionQueueItem):
               res_list.append(item)
        return res_list

    def get_selected_task_nodes(self):
        """
        Descript. :
        """
        res_list = []
        for item in self.get_selected_items():
            if isinstance(item,  Qt4_queue_item.DataCollectionGroupQueueItem):
               res_list.append(item)
        return res_list

    def is_sample_selected(self):
        """
        Descript. :
        """
        items = self.get_selected_items()
        
        for item in items:
            if isinstance(item, Qt4_queue_item.SampleQueueItem):
                return True
        return False

    def get_mounted_sample_item(self):
        it = QtGui.QTreeWidgetItemIterator(self.sample_tree_widget)
        item = it.value()

        while item:
           if isinstance(item, Qt4_queue_item.SampleQueueItem):
              if item.mounted_style:
                  return item
           it += 1
           item = it.value()

    def filter_sample_list(self, option):
        """
        Descript. :
        """
        self.sample_tree_widget.clearSelection()
        self.beamline_setup_hwobj.set_plate_mode(False)
        self.confirm_dialog.set_plate_mode(False)      
        self.sample_mount_method = option
        if option == SC_FILTER_OPTIONS.SAMPLE_CHANGER:
            self.sample_tree_widget.clear()
            self.queue_model_hwobj.select_model('ispyb')
            self.set_sample_pin_icon()
        elif option == SC_FILTER_OPTIONS.PLATE:
            self.sample_tree_widget.clear()
            self.queue_model_hwobj.select_model('plate')
            self.set_sample_pin_icon()
        elif option == SC_FILTER_OPTIONS.MOUNTED_SAMPLE:
            loaded_sample_loc = None

            if self.beamline_setup_hwobj.diffractometer_hwobj.\
                in_plate_mode():
                try:
                   loaded_sample = self.beamline_setup_hwobj.\
                       plate_manipulator_hwobj.getLoadedSample()
                   loaded_sample_loc = loaded_sample.getCoords()
                except:
                   pass
            else:
                try:
                   loaded_sample = self.beamline_setup_hwobj.\
                       sample_changer_hwobj.getLoadedSample()
                   loaded_sample_loc = loaded_sample.getCoords() 
                except:
                   pass
            it = QtGui.QTreeWidgetItemIterator(self.sample_tree_widget)
            item = it.value()
        
            while item:
                if isinstance(item, Qt4_queue_item.SampleQueueItem):
                    #TODO fix this to actual plate sample!!!
                    if item.get_model().location == loaded_sample_loc:
                        item.setSelected(True)
                        item.setHidden(False)
                    else:
                        item.setHidden(True)

                it += 1
                item = it.value()

            self.hide_empty_baskets()

        elif option == SC_FILTER_OPTIONS.FREE_PIN:
            self.sample_tree_widget.clear()
            self.queue_model_hwobj.select_model('free-pin')
            self.set_sample_pin_icon()
        self.sample_tree_widget_selection()
        
    def set_centring_method(self, method_number):       
        """
        Descript. :
        """
        self.centring_method = method_number

        try:
            dm = self.beamline_setup_hwobj.diffractometer_hwobj
        
            if self.centring_method == CENTRING_METHOD.FULLY_AUTOMATIC:
                dm.user_confirms_centring = False
            else:
                dm.user_confirms_centring = True
        except AttributeError:
            #beamline_setup_hwobj not set when method called
            pass

    def continue_button_click(self):
        """
        Descript. :
        """
        if self.queue_hwobj.is_executing():
            if not self.queue_hwobj.is_paused():
                self.queue_hwobj.set_pause(True)
            else:
                self.queue_hwobj.set_pause(False)

    def queue_paused_handler(self, state):
        """
        Descript. :
        """
        if state:
            self.parent().enable_hutch_menu(True)
            self.parent().enable_command_menu(True)
            self.parent().enable_task_toolbox(True)
            self.continue_button.setText('Continue')
            Qt4_widget_colors.set_widget_color(self.continue_button, 
                                               Qt4_widget_colors.LIGHT_YELLOW, 
                                               QtGui.QPalette.Button)
        else:
            self.parent().enable_hutch_menu(False)
            self.parent().enable_command_menu(False)
            self.parent().enable_task_toolbox(False)
            self.continue_button.setText('Pause')
            Qt4_widget_colors.set_widget_color(
                              self.continue_button, 
                              Qt4_widget_colors.BUTTON_ORIGINAL, 
                              QtGui.QPalette.Button)

    def collect_stop_toggle(self):
        """
        Descript. :
        """
        checked_items = self.get_checked_items()
        self.queue_hwobj.disable(False)

        path_conflict = self.check_for_path_collisions()     

        if path_conflict:
            self.queue_hwobj.disable(True)
        
        if self.queue_hwobj.is_disabled():
            logging.getLogger("GUI").\
                error('Can not start collect, see the tasks marked' +\
                      ' in the tree and solve the prorblems.')
            
        elif not self.collecting:
            # Unselect selected items.
            selected_items = self.get_selected_items()
            for item in selected_items:
                item.setSelected(False)
                #self.sample_tree_widget.setSelected(item, False)
            
            if len(checked_items):
                self.confirm_dialog.set_items(checked_items)
                self.confirm_dialog.show()
            else:
                message = "No data collections selected, please select one" + \
                          " or more data collections"

                QtGui.QMessageBox.information(self,"Data collection",
                                              message, "OK")
        else:
            self.stop_collection()

    def enable_sample_changer_widget(self, state):
        """
        Descript. :
        """
        self.parent().sample_changer_widget.centring_cbox.setEnabled(state)
        self.parent().sample_changer_widget.filter_cbox.setEnabled(state)

    def is_mounted_sample_item(self, item):
        """
        Descript. :
        """
        result = False

        if isinstance(item, Qt4_queue_item.SampleQueueItem):
            if item.get_model().free_pin_mode == True:
                result = True
            elif self.beamline_setup_hwobj.diffractometer_hwobj.in_plate_mode():
                if self.beamline_setup_hwobj.plate_manipulator_hwobj is not None:
                    if not self.beamline_setup_hwobj.plate_manipulator_hwobj.hasLoadedSample():
                       result = False
                    #TODO remove :2 and check full location
                    elif item.get_model().location == self.beamline_setup_hwobj.\
                             plate_manipulator_hwobj.getLoadedSample().getCoords():
                       result = True
            elif self.beamline_setup_hwobj.sample_changer_hwobj is not None:
                if not self.beamline_setup_hwobj.sample_changer_hwobj.hasLoadedSample():
                    result = False
                elif item.get_model().location == self.beamline_setup_hwobj.\
                        sample_changer_hwobj.getLoadedSample().getCoords():
                    result = True
        return result

    def collect_items(self, items = [], checked_items = []):
        """
        Descript. :
        """
        self.beamline_setup_hwobj.shape_history_hwobj.de_select_all()
        for item in checked_items:
            # update the run-number text incase of re-collect
            #item.setText(0, item.get_model().get_name())

            #Clear status
            item.setText(1, "")
            item.reset_style()
        
        self.user_stopped = False
        self.delete_button.setEnabled(False)
        self.enable_sample_changer_widget(False)
        self.collecting = True
        self.collect_button.setText(" Stop   ")
        Qt4_widget_colors.set_widget_color(
                          self.collect_button, 
                          Qt4_widget_colors.LIGHT_RED,
                          QtGui.QPalette.Button)
        self.collect_button.setIcon(self.stop_icon)
        self.continue_button.setEnabled(True)
        self.parent().enable_hutch_menu(False)
        self.run_cb()

        QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        try:
            self.queue_hwobj.execute()
        except (Exception, e):
            raise e
        
    def stop_collection(self):
        """
        Descript. :
        """
        QtGui.QApplication.restoreOverrideCursor()
        self.queue_hwobj.stop()
        self.queue_stop_handler()

    def queue_stop_handler(self, status = None):
        """
        Descript. :
        """
        QtGui.QApplication.restoreOverrideCursor()
        self.user_stopped = True
        self.queue_execution_completed(None)

    def queue_entry_execution_started(self, queue_entry):
        view_item = queue_entry.get_view()

        if isinstance(view_item, Qt4_queue_item.EnergyScanQueueItem):
            self.tree_brick.show_energy_scan_tab(view_item)  
        elif isinstance(view_item, Qt4_queue_item.XRFSpectrumQueueItem):
            self.tree_brick.show_xrf_spectrum_tab(view_item)
        elif isinstance(view_item, Qt4_queue_item.DataCollectionQueueItem):
            data_collection = view_item.get_model()
            if data_collection.is_mesh():
                self.tree_brick.show_advanced_tab(view_item)

        self.sample_tree_widget.clearSelection() 
        view_item.setSelected(True)

    def queue_entry_execution_finished(self, queue_entry, status):
        view_item = queue_entry.get_view()
        item_model = queue_entry.get_data_model()

        item_type = None
        item_icon = None
        item_details = ""

        if isinstance(view_item, Qt4_queue_item.DataCollectionQueueItem):
            collect_par = item_model.as_dict()
            item_details = "%d images" % collect_par["num_images"]
            if item_model.is_helical():
                item_type = "Helical"
                item_icon = "Line"
            elif item_model.is_mesh():
                item_type = "Mesh"
                item_icon = "Grid"
            else:
                item_type = "OSC"
                item_icon = "Point"
        elif isinstance(view_item, Qt4_queue_item.EnergyScanQueueItem):
            item_type = "Energy scan"
            item_icon = "EnergyScan2"
        elif isinstance(view_item, Qt4_queue_item.XRFSpectrumQueueItem):
            item_type = "XRF spectrum"
            item_icon = "LineGraph"

        if item_type:
            info_str_list = QtCore.QStringList()
            info_str_list.append(datetime.now().strftime("%H:%M:%S"))
            info_str_list.append(item_type)
            info_str_list.append(status)
            info_str_list.append(item_details)

            temp_treewidget_item = QtGui.QTreeWidgetItem(info_str_list)
            if status != "Successful": 
                for row in range(4):
                    temp_treewidget_item.setBackgroundColor(row, Qt4_widget_colors.LIGHT_RED)
            if item_icon:
                temp_treewidget_item.setIcon(0, Qt4_Icons.load_icon(item_icon))
            self.history_tree_widget.insertTopLevelItem(0, temp_treewidget_item)

        self.delete_empty_finished_items()

    def queue_execution_completed(self, status):
        """
        Restores normal cursors, changes collect button
        Deselects all items and selects mounted sample
        """
        QtGui.QApplication.restoreOverrideCursor() 
        self.collecting = False
        self.collect_button.setText("Collect Queue")
        self.collect_button.setIcon(self.play_icon)
        self.continue_button.setEnabled(False)
        Qt4_widget_colors.set_widget_color(
                          self.collect_button,
                          Qt4_widget_colors.LIGHT_GREEN,
                          QtGui.QPalette.Button)
        self.delete_button.setEnabled(True)
        self.enable_sample_changer_widget(True)
        self.parent().enable_hutch_menu(True)
        self.parent().enable_command_menu(True)
        self.parent().enable_task_toolbox(True)
 
        self.sample_tree_widget.clearSelection()
        sample_item = self.get_mounted_sample_item()
        sample_item.setSelected(True)
        self.set_sample_pin_icon()

    def get_checked_items(self):
        """
        Descript. :
        """
        checked_items = []
        it = QtGui.QTreeWidgetItemIterator(self.sample_tree_widget)
        item = it.value()
        while item: 
            if item.checkState(0) > 0:
               checked_items.append(item)   
            it += 1
            item = it.value()
        return checked_items

    def copy_click(self, selected_items = None):
        """
        Descript. :
        """
        if not isinstance(selected_items, list):
            selected_items = self.get_selected_items()

        for item in selected_items:
            if type(item) not in (Qt4_queue_item.BasketQueueItem,
                                  Qt4_queue_item.SampleQueueItem,
                                  Qt4_queue_item.DataCollectionGroupQueueItem):
                new_node = self.queue_model_hwobj.copy_node(item.get_model())
                new_node.acquisitions[0].acquisition_parameters.\
                centred_position.snapshot_image = self.beamline_setup_hwobj.\
                shape_history_hwobj.get_scene_snapshot()
                self.queue_model_hwobj.add_child(item.get_model().get_parent(), new_node)
        self.sample_tree_widget_selection()
 
    def delete_click(self, selected_items = None):
        """
        Descript. :
        """
        children = []

        if not isinstance(selected_items, list):
            selected_items = self.get_selected_items()

        for item in selected_items:
            parent = item.parent()
            if item.deletable and parent:
                if not parent.isSelected() or (not parent.deletable):
                    self.tree_brick.show_sample_centring_tab()

                    self.queue_model_hwobj.del_child(parent.get_model(),
                                                     item.get_model())
                    qe = item.get_queue_entry()
                    parent.get_queue_entry().dequeue(qe)
                    parent.takeChild(parent.indexOfChild(item))

                    if not parent.child(0):
                        parent.setOn(False)
            else:
                item.reset_style()

                for index in range(item.childCount()):
                    children.append(item.child(index)) 

        if children:
            self.delete_click(selected_items = children)

        self.check_for_path_collisions()
        self.set_first_element()

    def set_first_element(self):
        """
        Descript. :
        """
        selected_items = self.get_selected_items()
        if len(selected_items) == 0:        
            it = QtGui.QTreeWidgetItemIterator(self.sample_tree_widget)
            #item = it.current()
            item = it.value()
            if item.get_model().free_pin_mode:
                self.sample_tree_widget.topLevelItem(0).setSelected(True)
                #self.sample_tree_widget.setSelected(self.sample_list_view.firstChild(), True)

    def down_click(self):
        """
        Descript. :
        """
        selected_items = self.get_selected_items()

        if len(selected_items) == 1:
            item = selected_items[0]

            if isinstance(item, Qt4_queue_item.QueueItem):
                if item.treeWidget().itemBelow(item) is not None:
                    item.move_item(item.treeWidget().itemBelow(item))
                    self.sample_tree_widget_selection()

    def previous_sibling(self, item):
        """
        Descript. :
        """
        if item.parent():
            first_child = item.parent().child(0)
        else:
            first_child = item.treeWidget().topLevelItem(0) 

        if first_child is not item :
            sibling = first_child.treeWidget().itemBelow(first_child) 
            #sibling = first_child.nextSibling()   
        
            while sibling:           
                if sibling is item :
                    return first_child
                #elif sibling.nextSibling() is item:
                elif first_child.treeWidget().itemBelow(first_child) is item:
                    return sibling
                else:
                    sibling = first_child.treeWidget().itemBelow(first_child)
                    #sibling = sibling.nextSibling()
        else :
            return None
        
    def up_click(self):
        """
        Descript. :
        """
        selected_items = self.get_selected_items()

        if len(selected_items) == 1:
            item = selected_items[0]

            if isinstance(item, Qt4_queue_item.QueueItem): 
                #older_sibling = self.previous_sibling(item)
                older_sibling = self.sample_tree_widget.itemAbove(item)
                if older_sibling:
                    older_sibling.move_item(item)
                    self.sample_tree_widget_selection()

    def samples_from_sc_content(self, sc_basket_content, sc_sample_content):
        """
        Descript. :
        """
        basket_list = []
        sample_list = []
        for basket_info in sc_basket_content:
            basket = queue_model_objects.Basket()
            basket.init_from_sc_basket(basket_info, basket_info[2])
            basket_list.append(basket)
        for sample_info in sc_sample_content:
            sample = queue_model_objects.Sample()
            sample.init_from_sc_sample(sample_info)
            sample_list.append(sample)
        return basket_list, sample_list

    """
    def samples_from_plate_content(self, plate_row_content, plate_sample_content):
        row_list = []
        sample_list = []

        for row_info in plate_row_content:
            basket = queue_model_objects.Basket()
            basket.init_from_sc_basket(row_info, row_info[2])
            row_list.append(basket)
        for sample_info in plate_sample_content:
            sample = queue_model_objects.Sample()
            sample.init_from_sc_sample(sample_info)
            sample_list.append(sample)
        return row_list, sample_list
    """

    def samples_from_lims(self, lims_sample_list):
        """
        Descript. :
        """
        barcode_samples = {}
        location_samples = {}

        for lims_sample in lims_sample_list:
            sample = queue_model_objects.Sample()
            sample.init_from_lims_object(lims_sample)

            if sample.lims_code:
                barcode_samples[sample.lims_code] = sample
                
            if sample.lims_location:
                location_samples[sample.lims_location] = sample
            
        return (barcode_samples, location_samples)

    def enqueue_samples(self, sample_list):
        """
        Descript. :
        """
        for sample in sample_list:
            self.queue_model_hwobj.add_child(self.queue_model_hwobj.\
                                             get_model_root(), sample)
            self.add_to_queue([sample], self.sample_tree_widget, False)

    def populate_free_pin(self, sample=None):
        """
        Descript. :
        """
        self.queue_model_hwobj.clear_model('free-pin')
        self.queue_model_hwobj.select_model('free-pin')
        if sample is None:
            sample = queue_model_objects.Sample()
            sample.set_name('manually-mounted')
        sample.free_pin_mode = True
        self.queue_model_hwobj.add_child(self.queue_model_hwobj.get_model_root(),
                                         sample)
        self.set_sample_pin_icon()

    def populate_tree_widget(self, basket_list, sample_list, sample_changer_num):   
        """
        Descript. :
        """
        #Make this better
        if sample_changer_num == 1:
            mode_str = "ispyb"
        else:
            mode_str = "plate" 
        self.queue_hwobj.clear()
        self.queue_model_hwobj.clear_model(mode_str)
        self.sample_tree_widget.clear()
        self.queue_model_hwobj.select_model(mode_str)

        for basket_index, basket in enumerate(basket_list):
            self.queue_model_hwobj.add_child(self.queue_model_hwobj.\
                                             get_model_root(), basket)
            basket.set_enabled(False)
            for sample in sample_list:
                if sample.location[0] == basket_index + 1:
                    basket.add_sample(sample)
                    self.queue_model_hwobj.add_child(basket, sample)
                    sample.set_enabled(False)
        self.set_sample_pin_icon()

    def set_sample_pin_icon(self):
        """
        Descript. :
        """
        it = QtGui.QTreeWidgetItemIterator(self.sample_tree_widget)
        item = it.value()

        while item:
            if self.is_mounted_sample_item(item):
                item.setSelected(True)
                item.set_mounted_style(True)
                #self.sample_tree_widget.scrollTo(self.sample_tree_widget.\
                #     indexFromItem(item))
            elif isinstance(item, Qt4_queue_item.SampleQueueItem):
                item.set_mounted_style(False)

            if isinstance(item, Qt4_queue_item.SampleQueueItem):
                if item.get_model().lims_location != (None, None):
                    if not self.is_mounted_sample_item(item):
                        item.setIcon(0, self.ispyb_icon)
                    item.setText(0, item.get_model().loc_str + ' - ' \
                                 + item.get_model().get_display_name())
            elif isinstance(item, Qt4_queue_item.BasketQueueItem):
                #pass
                item.setText(0, item.get_model().get_display_name())
                """
                do_it = True
                child_item = item.child(0)
                while child_item:
                    if child_item.child(0):
                        do_it = False
                        break
                    child_item = self.sample_tree_widget.itemBelow(child_item)
                if do_it:
                    item.setOn(False)        
                """
            it += 1
            item = it.value()

    def check_for_path_collisions(self):
        """
        Descript. :
        """
        conflict = False
        it = QtGui.QTreeWidgetItemIterator(self.sample_tree_widget)
        item = it.value()

        while item:
            if item.checkState(0) == QtCore.Qt.Checked:
                pt = item.get_model().get_path_template()
                
                if pt:
                     path_conflict = self.queue_model_hwobj.\
                                check_for_path_collisions(pt)

                     if path_conflict:
                         conflict = True
                         item.setIcon(0, self.caution_icon)
                     else:
                         item.setIcon(0, QtGui.QIcon())
                         
            it += 1
            item = it.value()

        return conflict

    def select_last_added_item(self):
        if self.last_added_item:
            self.sample_tree_widget.clearSelection()
            self.last_added_item.setSelected(True) 

    def hide_empty_baskets(self):
        item_iterator = QtGui.QTreeWidgetItemIterator(\
             self.sample_tree_widget)
        item = item_iterator.value()
        while item:
              hide = True

              if type(item) in(Qt4_queue_item.BasketQueueItem,
                               Qt4_queue_item.DataCollectionGroupQueueItem):
                  for index in range(item.childCount()):
                      if not item.child(index).isHidden():
                          hide = False
                          break
                  item.setHidden(hide)

              item_iterator += 1
              item = item_iterator.value()

    def delete_empty_finished_items(self):
        item_iterator = QtGui.QTreeWidgetItemIterator(\
             self.sample_tree_widget)
        item = item_iterator.value()
        while item:
              #if type(item) in(Qt4_queue_item.BasketQueueItem,
              #                 Qt4_queue_item.DataCollectionGroupQueueItem):
              #    for index in range(item.childCount()):
              #        if not item.child(index).isHidden():
              #            hide = False
              #            break
              #    item.setHidden(hide)
              item_iterator += 1
              item = item_iterator.value()

    def cut_item(self):
        """Cut selected item"""

        item = self.sample_tree_widget.currentItem()
        self.item_copy = (item.get_model(), True)
        self.delete_click([item])

    def copy_item(self):
        """Makes a copy of the selected item"""

        item = self.sample_tree_widget.currentItem()
        self.item_copy = (item.get_model(), False)

    def paste_item(self, new_node=None):
        """Paste item. If item was cut then remove item from clipboard"""

        for item in self.get_selected_items():
            parent_nodes = []
            if new_node is None:
                new_node = self.queue_model_hwobj.copy_node(self.item_copy[0])
            else:
                #we have to update run number
                new_node.acquisitions[0].path_template.run_number = \
                    self.queue_model_hwobj.get_next_run_number(\
                    new_node.acquisitions[0].path_template)

            new_node.acquisitions[0].acquisition_parameters.\
                centred_position.snapshot_image = self.beamline_setup_hwobj.\
                shape_history_hwobj.get_scene_snapshot() 

            if isinstance(item, Qt4_queue_item.DataCollectionQueueItem):
                parent_nodes = [item.get_model().get_parent()]
            elif isinstance(item, Qt4_queue_item.DataCollectionGroupQueueItem):
                parent_nodes = [item.get_model()]
            elif isinstance(item, Qt4_queue_item.SampleQueueItem):
                #If sample was selected then a new task group is created
                parent_nodes = [self.create_task_group(item.get_model())]
            elif isinstance(item, Qt4_queue_item.BasketQueueItem): 
                for sample in item.get_model().get_sample_list():
                    parent_nodes.append(self.create_task_group(sample))
                
            for parent_node in parent_nodes:
                self.queue_model_hwobj.add_child(parent_node, new_node)
        self.sample_tree_widget_selection()

        if self.item_copy[1]:
            self.item_copy = None
        
    def save_item(self):
        """Saves a single item in a file"""

        filename = str(QtGui.QFileDialog.getSaveFileName(\
            self, "Choose a filename to save selected item",
            os.environ["HOME"]))
        if not filename.endswith(".dat"):
            filename += ".dat"

        save_file = None
        try:
           save_file = open(filename, 'w')
           items_to_save = []
           for item in self.get_selected_items():
               items_to_save.append(item.get_model())
           save_file.write(jsonpickle.encode(items_to_save))
        except:
           logging.getLogger().exception("Cannot save file %s", filename)
           if save_file:
               save_file.close()

    def load_item(self):
        """Load item from a template saved in a file"""

        items_to_apply = self.get_selected_items()
        self.insert_item(apply_once=True)
        self.delete_click(items_to_apply)     

    def insert_item(self, apply_once=False):
        """Inserts item from a file"""

        filename = str(QtGui.QFileDialog.getOpenFileName(self,
            "Open file", os.environ["HOME"],
            "Item file (*.dat)", "Choose a itemfile to open"))
        if len(filename) > 0:
            load_file = None
            try: 
                load_file = open(filename, 'r')
                for item in jsonpickle.decode(load_file.read()):
                    self.item_copy = (item, True)
                    self.paste_item(item)
                    if apply_once:
                        break
            except:
                logging.getLogger().exception(\
                    "Cannot insert an item from file %s", filename)
                if load_file:
                    load_file.close() 

    def create_task_group(self, sample_item_model, ref_item=None):
        task_group_node = queue_model_objects.TaskGroup()
        
        #This is ugly and could be much nicer
        if isinstance(self.item_copy[0], queue_model_objects.DataCollection):
            if self.item_copy[0].is_helical():
                group_name = "Helical"
            elif self.item_copy[0].is_mesh():
                group_name = "Advanced"
            else:
                group_name = "Standart"
        elif isinstance(self.item_copy[0], queue_model_objects.Characterisation):
            group_name = "Characterisation" 
        elif isinstance(self.item_copy[0], queue_model_objects.EnergyScan):
            group_name = "Energy scan"
        elif isinstance(self.item_copy[0], queue_model_objects.XRFSpectrum):
            group_name = "XRF spectrum"

        task_group_node.set_name(group_name)
        num = sample_item_model.get_next_number_for_name(group_name)
        task_group_node.set_number(num)
            
        self.queue_model_hwobj.add_child(sample_item_model, task_group_node)

        return task_group_node
