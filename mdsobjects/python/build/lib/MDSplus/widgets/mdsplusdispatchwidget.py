from gtk import VBox
from MDSplus.widgets.mdspluserrormsg import MDSplusErrorMsg
from MDSplus.widgets.mdsplussequentialwidget import MDSplusSequentialWidget
from MDSplus.widgets.mdsplusexpressionwidget import MDSplusExpressionWidget
from MDSplus.widgets.mdsplusdtypeselwidget import MDSplusDtypeSelWidget

class MDSplusDispatchWidget(MDSplusDtypeSelWidget,VBox):

    def __init__(self,value=None):
        super(MDSplusDispatchWidget,self).__init__(homogeneous=False,spacing=10)
        self.menu=self.dtype_menu(("Dispatch",))
        self.dispatch=MDSplusSequentialWidget()
        self.expression=MDSplusExpressionWidget()
        self.expression.set_no_show_all(True)
        self.widgets=(self.dispatch,self.expression)
        self.pack_start(self.menu,False,False,0)
        self.pack_start(self.dispatch,False,False,0)
        self.pack_start(self.expression,False,False,0)
        self.value=value
            
