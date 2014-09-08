import numpy as _NP
import ctypes as _C
from ctypes.util import find_library as _find_library
import os as _os
import copy as _copy
import sys as _sys

debug=False

if _sys.version_info[0] >= 3:
  buffer=memoryview

if '__package__' not in globals() or __package__ is None or len(__package__)==0:
  def _mimport(name,level):
    return __import__(name,globals())
else:
  def _mimport(name,level):
    return __import__(name,globals(),{},[],level)

def _loadLib(name):
    libnam=_find_library(name)
    if _sys.version_info[0]==2 and _sys.version_info[1]<5 and _os.name=='posix' and _sys.platform.startswith('linux'):
      return _C.CDLL('lib'+name+'.so')
    if libnam is None:
        raise Exception("Error finding library: "+name)
    else:
        try:
            lib=_C.CDLL(libnam)
        except:
            try:
                lib=_C.CDLL(name)
            except:
                lib=_C.CDLL(_os.path.basename(libnam))
    return lib

_MdsShr=_loadLib('MdsShr')
try:
  _TdiShr=_loadLib('TdiShr')
  _Mdsdcl=_loadLib('Mdsdcl')
  _tcl_commands=_loadLib('tcl_commands')
except:
  pass
_MdsGetMsg=_MdsShr.MdsGetMsg
_MdsGetMsg.argtypes=[_C.c_int32]
_MdsGetMsg.restype=_C.c_char_p



def TCL(cmd=None,noraise=True,noout=False):
  """Tree Command Language (TCL) command execution
  @param cmd: TCL command line
  @type cmd: str
  """
  if cmd is None:
    try:
      ncmd=raw_input('TCL> ')
      while not str(ncmd).lower().startswith('exit'):
        TCL(ncmd)
        ncmd=raw_input('TCL> ')
      return
    except EOFError:
      return
  if cmd.lower().startswith('exit'):
    return None
  _Mdsdcl.mdsdcl_do_command(_C.c_char_p(str.encode('set command tcl_commands/def_file="*.tcl"')))
  _tcl_commands.TclSaveOut()
  status = _Mdsdcl.mdsdcl_do_command(_C.c_char_p(str.encode(cmd)))
  tlen=_tcl_commands.TclOutLen()
  txt=''
  if tlen > 0:
    txt=(_C.c_byte*tlen)()
    lenout=_tcl_commands.TclGetOut(_C.c_int32(1),_C.c_int32(tlen),txt)
    if lenout > 0:
      txt=str(_NP.array(txt[:],dtype=_NP.uint8).tostring().decode())
  if (status & 1)==0:
    msg=getStatusMsg(status)
    if not noraise:
      raise MdsException(msg)
    else:
      txt=msg
  if not noout:
    if len(txt) > 0:
      print(txt)
  else:
    return txt

def getStatusMsg(status,default=None):
    status=int(status)
    if status==0 and not default is None:
        return default
    try:
        return _MdsGetMsg(status).decode()
    except:
        return _MdsGetMsg(status)

def getUnits(item):
    """Return units of item. Evaluate the units expression if necessary.
    @rtype: string"""
    try:
        return item.units
    except:
        return ""
    
def getError(item):
    """Return the data of the error of an object
    @rtype: Data"""
    try:
        return item.error
    except:
        return None

def getValuePart(item):
    """Return the value portion of an object
    @rtype: Data"""
#    tdibuiltins=_mimport('tdibuiltins',1)
    try:
        return _tdi.VALUE_OF(makeData(item)).evaluate()
    except:
        return None

def getDimension(item,idx=0):
    """Return dimension of an object
    @rtype: Data"""
#    tdibuiltins=_mimport('tdibuiltins',1)
    try:
        return _tdi.DIM_OF(makeData(item),makeData(idx)).evaluate()
    except:
        return None

def data(item):
    """Return the data for an object converted into a primitive data type
    @rtype: Data"""
#    tdibuiltins=_mimport('tdibuiltins',1)
    return _tdi.DATA(makeData(item)).evaluate().value

def decompile(item):
    """Returns the item converted to a string
    @rtype: string"""
    return makeData(item).decompile()

def evaluate(item,):
    """Return evaluation of mdsplus object"""
    try:
        return item.evaluate()
    except:
        return item

def rawPart(item):
    """Return raw portion of data item"""
    try:
        return item.raw
    except:
        return None

def makeData(value):
    """Convert a python object to a MDSobject Data object"""
    if value is None:
        return EmptyData()
    if isinstance(value,Data):
        return value
    if isinstance(value,(_NP.generic,_C._SimpleCData,int,float,str,complex)):
        return makeScalar(value)
    try:
      if isinstance(value,long):
        return makeScalar(value)
    except:
      pass
    if isinstance(value,type(_C.c_int64(0).value)): #### special handling for python2 and 3 compatibility
      return makeScalar(value)
    if isinstance(value,tuple) or isinstance(value,list):
        return List(value)
    if isinstance(value,(_NP.ndarray,_C.Array)):
        return makeArray(value)
    if isinstance(value,dict):
        return Dictionary(value)
    else:
        import traceback
        traceback.print_stack()
        raise TypeError('Cannot make MDSplus data type from type: %s' % (str(type(value)),))

class _Descriptor(_C.Structure):
  """MDSplus internals descriptor structure for describing scalar values"""
  _fields_=[("length",_C.c_ushort),
            ("dtype",_C.c_ubyte),
            ("dclass",_C.c_ubyte),
            ("pointer",_C.c_void_p),]
  def _getValue(self):
    if debug:
      print "Descriptor dtype=%d" % (self.dtype,)
      print "Descriptor class=%d" % (self.dclass,)
      print "Descriptor length=%d" % (self.length,)
      if self.pointer is None:
        print "Descriptor pointer=None"
      else:
        print "Descriptor pointer=%d" % (self.pointer,)
    if self.dtype == 24:
      if self.pointer == _C.c_void_p(0):
        return None
      d = _C.cast(self.pointer,_C.POINTER(_Descriptor)).contents
      if hasattr(self,'tree'):
        d.tree=self.tree
      return d.value
    elif self.dclass == 195: #### Compressed array
      xd=_Descriptor_xd()
      status = _MdsShr.MdsDecompress(_C.pointer(self),_C.pointer(xd))
      if (status & 1)==0:
        raise MdsException('Error decompressing array: %s' % (getStatusMessage(status),))
      else:
        return _C.cast(_C.pointer(xd),_C.POINTER(_Descriptor)).contents.value
    elif self.dclass in Data.mdsclassToClass:
      return Data.mdsclassToClass[self.dclass]._dataFromDescriptor(self)
    raise TdiException('Unknown descriptor class %d' % self.dclass)
  value=property(_getValue,)

class _Descriptor_a(_C.Structure):
  """MDSplus internals descriptor structure for describing arrays"""
  if _os.name=='nt':
    _fields_=[("length",_C.c_ushort),("dtype",_C.c_ubyte),("dclass",_C.c_ubyte),
              ("pointer",_C.c_void_p),("scale",_C.c_byte),("digits",_C.c_ubyte),
              ("aflags",_C.c_ubyte),("dimct",_C.c_ubyte),("arsize",_C.c_uint),
              ("a0",_C.c_void_p),("coeff_and_bounds",_C.c_int32 * 24)]
  else:
    _fields_=[("length",_C.c_ushort),("dtype",_C.c_ubyte),("dclass",_C.c_ubyte),
              ("pointer",_C.c_void_p),("scale",_C.c_byte),("digits",_C.c_ubyte),
              ("fill1",_C.c_ushort),("aflags",_C.c_ubyte),("fill2",_C.c_ubyte * 3),
              ("dimct",_C.c_ubyte),("arsize",_C.c_uint),("a0",_C.c_void_p),
              ("coeff_and_bounds",_C.c_int32 * 24)]

  def __getattr__(self,name):
    if name == 'binscale':
      return not ((self.aflags & 8) == 0)
    elif name == 'redim':
      return not ((self.aflags & 16) == 0)
    elif name == 'column':
      return not ((self.aflags & 32) == 0)
    elif name == 'coeff':
      return not ((self.aflags & 64) == 0)
    elif name == 'bounds':
      return not ((self.aflags & 128) == 0)
    else:
      return super(_Descriptor_a,self).__getattribute__(name)
        
  def __setattr__(self,name,value):
    if name == 'binscale':
      if value == 0:
        self.aflags = self.aflags & ~8
      else:
        self.aflags = self.aflags | 8
    elif name == 'redim':
      if value == 0:
        self.aflags = self.aflags & ~16
      else:
        self.aflags = self.aflags | 16
    elif name == 'column':
      if value == 0:
        self.aflags = self.aflags & ~32
      else:
        self.aflags = self.aflags | 32
    elif name == 'coeff':
      if value == 0:
        self.aflags = self.aflags & ~64
      else:
        self.aflags = self.aflags | 64
    elif name == 'bounds':
      if value == 0:
        self.aflags = self.aflags & ~128
      else:
        self.aflags = self.aflags | 128
    else:
      return super(_Descriptor_a,self).__setattr__(name,value)


class _Descriptor_r(_C.Structure):
    if _os.name=='nt':
        _fields_=_Descriptor._fields_+[("ndesc",_C.c_ubyte),("fill1",_C.c_ubyte*4),("dscptrs",_C.c_void_p*256)]
    else:
        _fields_=_Descriptor._fields_+[("ndesc",_C.c_ubyte),("fill1",_C.c_ubyte*3),("dscptrs",_C.c_void_p*256)]

def _descrWithUnitsAndError(obj,descr):
  if hasattr(obj,'_units'):
    newd=_Descriptor_r()
    newd.dtype=211
    newd.length=0
    newd.dclass=Compound.mdsclass
    newd.pointer=_C.c_void_p(0)
    newd.ndesc=2
    newd.dscptrs[0]=_C.cast(_C.pointer(descr),_C.c_void_p)
    newd.dscptrs[1]=_C.cast(_C.pointer(makeData(obj._units).descriptor),_C.c_void_p)
    newd.original=(obj,descr)
    descr=newd
  if hasattr(obj,'_error'):
    newd=_Descriptor_r()
    newd.dtype=213
    newd.length=0
    newd.dclass=Compound.mdsclass
    newd.pointer=_C.c_void_p(0)
    newd.ndesc=2
    newd.dscptrs[0]=_C.cast(_C.pointer(descr),_C.c_void_p)
    newd.dscptrs[1]=_C.cast(_C.pointer(makeData(obj._error).descriptor),_C.c_void_p)
    newd.original=(obj,descr)
    descr=newd
  return descr

class _Descriptor_xd(_C.Structure):
    _fields_=_Descriptor._fields_+[("l_length",_C.c_uint)]
    
    def __init__(self):
        self.l_length=0
        self.length=0
        self.pointer=None
        self.dclass=192

    def __str__(self):
        return str(_C.cast(_C.pointer(self),_C.POINTER(_Descriptor)).contents)+" l_length="+str(self.l_length)

    def _getValue(self):
        if self.l_length==0:
          return None
        else:
          d = _C.cast(_C.pointer(self),_C.POINTER(_Descriptor)).contents
          if hasattr(self,'tree'):
            d.tree=self.tree
          return d.value
    value=property(_getValue)

    def __del__(self):
        try:
          _MdsShr.MdsFree1Dx(_C.pointer(self),_C.c_void_p(0))
        except:
          pass

def TdiEvaluate(value):
  xd=_Descriptor_xd()
  try:
    _tree.Tree.lock()
    try:
      t=_tree.Tree(None)
    except:
      t=None
    if t is not None:
      t.restoreContext()
      xd.tree=t
    if value.showtdi:
      print("Using Tdi1Evaluate to evaluate: %s" % (value.__class__.__name__,))
    status=_TdiShr.TdiIntrinsic(158,1,_C.pointer(_C.pointer(value.descriptor)),_C.pointer(xd))
  finally:
    _tree.Tree.unlock()
  if (status & 1 != 0):
    return xd.value
  else:
    raise TdiException(getStatusMsg(status,"Error evaluating value"))

def DateToQuad(date):
  ans=_C.c_ulonglong(0)
  status = _MdsShr.LibConvertDateString(_C.c_char_p(str.encode(date)),_C.pointer(ans))
  if not (status & 1):
    raise MdsException("Cannot parse %s as date. Use dd-mon-yyyy hh:mm:ss.hh format or \"now\",\"today\",\"yesterday\"." % (date,))
  return makeData(ans)

def QuadToDate(date):
  ans=String(' '*23)
  length=_C.c_int32(23)
  time=_C.c_uint64(Uint64(date).value)
  _MdsShr.LibSysAscTim(_C.pointer(length),_C.pointer(ans.descriptor),_C.pointer(time),_C.c_void_p(0))
  return ans

class Data(object):
    """Superclass used by most MDSplus objects. This provides default methods if not provided by the subclasses.
    """
    usePython='USE_PYTHON' in _os.environ
    showtdi=False
    mdsclassToClass=dict()

    loadLib=_loadLib
    Descriptor_xd=_Descriptor_xd
    
    def __init__(self,*value):
        """Cannot create instances of class Data objects. Use Data.makeData(initial-value) instead
        @raise TypeError: Raised if attempting to create an instance of Data
        @rtype: Data
        """
        raise TypeError('Cannot create \'Data\' instances')

    def value_of(self):
        """Return value part of object
        @rtype: Data"""
        return _tdi.VALUE_OF(self).evaluate()

    def raw_of(self):
        """Return raw part of object
        @rtype: Data"""
        return _tdi.RAW_OF(self).evaluate()
    
    def getDimensionAt(self,idx=0):
        """Return dimension of object
        @param idx: Index of dimension
        @type idx: int
        @rtype: Data"""
        return _tdi.DIM_OF(self,makeData(idx)).evaluate()
    
    dim_of=getDimensionAt
    
    def _getUnits(self):
        return _tdi.UNITS(self).evaluate()

    def _setUnits(self,units):
        if units is None:
            if hasattr(self,'_units'):
                delattr(self,'_units')
        else:
            self._units=units

    units=property(_getUnits,_setUnits)
    """
    The units of the Data instance.
    @type: String
    """

    def _decompile_units_and_error(self,ans,isstring=False):
        if isstring:
            outans=repr(ans)
        else:
            outans=ans
        if hasattr(self,"_units"):
            if hasattr(self,"_error"):
                ans='Build_With_Units(Build_With_Error(%s, %s), %s)' % (outans,repr(self._error),repr(self._units))
            else:
                ans='Build_With_Units(%s, %s)' % (outans,repr(self._units))
        elif hasattr(self,'_error'):
            ans='Build_With_Error(%s, %s)' % (outans,repr(self._error))
        return ans

    def _getError(self):
        return _tdi.ERROR_OF(self).evaluate()

    def _setError(self,error):
        if error is None:
            if hasattr(self,'_error'):
                delattr(self,'_error')
        else:
            self._error=error

    error=property(_getError,_setError)
    """
    The error vector to associate with the data.
    @type: Data
    """

    def _getHelp(self):
        return _tdi.HELP_OF(self).evaluate()

    def _setHelp(self,help):
        if help is None:
            if hasattr(self,'_help'):
                delattr(self,'_help')
        else:
            self._help=help

    help=property(_getHelp,_setHelp)
    """
    The help string associated with the data.
    @type: String
    """

    def _getValidation(self):
        return _tdi.VALIDATION_OF(self).evaluate()

    def _setValidation(self,validation):
        if validation is None:
            if hasattr(self,'_validation'):
                delattr(self,'_validation')
        else:
            self._validation=validation

    def setValidation(self,validation):
        self._setValidation(validation)
        return self

    validation=property(_getValidation,_setValidation)
    """
    A validation procedure for the data.
    Currently no built-in utilities make use of this validation property.
    One could envision storing an expression which tests the data and returns
    a result.
    @type: Data
    """                       
            
    def units_of(self):
        """Return units part of the object
        @rtype: Data"""
        return _tdi.UNITS_OF(self).evaluate()

    def __abs__(self):
        """
        Absolute value: x.__abs__() <==> abs(x)
        @rtype: Data
        """
        return _tdi.ABS(self).evaluate()

    def bool(self):
        """
        Return boolean
        @rtype: Bool
        """
        if isinstance(self,Array):
            return self._value!=0
        elif isinstance(self,Compound) and hasattr(self,'value_of'):
            return self.value_of().bool()
        else:
            ans=int(self)
            return (ans & 1) == 1
    __bool__=bool

    def __add__(self,y):
        """
        Add: x.__add__(y) <==> x+y
        @rtype: Data"""
        return _tdi.ADD(self,makeData(y)).evaluate()

    def __and__(self,y):
        """And: x.__and__(y) <==> x&y
        @rtype: Data"""
        return _tdi.IAND(self,makeData(y)).evaluate()

    def __div__(self,y):
        """Divide: x.__div__(y) <==> x/y
        @rtype: Data"""
        return _tdi.DIVIDE(self,makeData(y)).evaluate()

    __truediv__=__div__

    def __eq__(self,y):
        """Equals: x.__eq__(y) <==> x==y
        @rtype: Bool"""
        return _tdi.EQ(self,makeData(y)).evaluate().bool()

    def __hasBadTreeReferences__(self,tree):
        return False

    def __fixTreeReferences__(self,tree):
        return self

    def __float__(self):
        """Float: x.__float__() <==> float(x)
        @rtype: Data"""
        ans=_tdi.FLOAT(self).evaluate().value
        try:
            return float(ans[0])
        except:
            return float(ans)

    def __floordiv__(self,y):
        """Floordiv: x.__floordiv__(y) <==> x//y
        @rtype: Data"""
        return _tdi.FLOOR(self/y).evaluate()

    def __ge__(self,y):
        """Greater or equal: x.__ge__(y) <==> x>=y
        @rtype: Bool"""
        return _tdi.GE(self,makeData(y)).evaluate().bool()

    def __getitem__(self,y):
        """Subscript: x.__getitem__(y) <==> x[y]
        @rtype: Data"""
        if isinstance(y,slice):
            y=Range(y.start,y.stop,y.step)
        ans=_tdi.SUBSCRIPT(self,y).evaluate()
        if isinstance(ans,Array):
            if ans.shape[0]==0:
                raise IndexError
        return ans
    
    def __gt__(self,y):
        """Greater than: x.__gt__(y) <==> x>y
        @rtype: Bool"""
        return _tdi.GT(self,makeData(y)).evaluate().bool()

    def __int__(self):
        """Integer: x.__int__() <==> int(x)
        @rtype: int"""
        return int(self.getInt().value)

    def __invert__(self):
        """Binary not: x.__invert__() <==> ~x
        @rtype: Data"""
        return _tdi.INOT(self).evaluate()

    def __le__(self,y):
        """Less than or equal: x.__le__(y) <==> x<=y
        @rtype: Bool"""
        return _tdi.LE(self,makeData(y)).evaluate().bool()

    def __len__(self):
        """Length: x.__len__() <==> len(x)
        @rtype: Data
        """
        return int(_tdi.SIZE(self).evaluate().data())

    def __long__(self):
        """Convert this object to python long
        @rtype: long"""
        return long(self.getLong()._value)

    def __lshift__(self,y):
        """Lrft binary shift: x.__lshift__(y) <==> x<<y
        @rtype: Data"""
        return _tdi.SHIFT_LEFT(self,makeData(y)).evaluate()

    def __lt__(self,y):
        """Less than: x.__lt__(y) <==> x<y
        @rtype: Bool"""
        return _tdi.LT(self,makeData(y)).evaluate().bool()
    
    def __mod__(self,y):
        """Modulus: x.__mod__(y) <==> x%y
        @rtype: Data"""
        return _tdi.MOD(self,makeData(y)).evaluate()
    
    def __mul__(self,y):
        """Multiply: x.__mul__(y) <==> x*y
        @rtype: Data"""
        return _tdi.MULTIPLY(self,makeData(y)).evaluate()

    def __ne__(self,y):
        """Not equal: x.__ne__(y) <==> x!=y
        @rtype: Data"""
        return _tdi.NE(self,makeData(y)).evaluate().bool()

    def __neg__(self):
        """Negation: x.__neg__() <==> -x
        @rtype: Data"""
        return _tdi.UNARY_MINUS(self).evaluate()

    def __nonzero__(self):
        """Not equal 0: x.__nonzero__() <==> x != 0
        @rtype: Bool"""
        return self!=0

    def __or__(self,y):
        """Or: x.__or__(y) <==> x|y
        @rtype: Data"""
        return self

    def __pos__(self):
        """Unary plus: x.__pos__() <==> +x
        @rtype: Data"""
        return self

    def __radd__(self,y):
        """Reverse add: x.__radd__(y) <==> y+x
        @rtype: Data"""
        return makeData(y)+self

    def __rdiv__(self,y):
        """Reverse divide: x.__rdiv__(y) <==> y/x
        @rtype: Data"""
        return makeData(y)/self

    def __rfloordiv__(self,y):
        """x.__rfloordiv__(y) <==> y//x
        @rtype: Data"""
        return makeData(y)//self

    def __rlshift__(self,y):
        """Reverse left binary shift: x.__rlshift__(y) <==> y<<x
        @rtype: Data"""
        return makeData(y) << self

    def __rmod__(self,y):
        """Reverse modulus: x.__rmod__(y) <==> y%x
        @rtype: Data"""
        return makeData(y) % self

    def __rmul__(self,y):
        """Reverse multiply: x.__rmul__(y) <==> y*x
        @type: Data"""
        return makeData(y)*self

    def __ror__(self,y):
        """Reverse or: x.__ror__(y) <==> y|x
        @type: Data"""
        return makeData(y) or self

    def __rrshift__(self,y):
        """Reverse right binary shift: x.__rrshift__(y) <==> y>>x
        @rtype: Data"""
        return makeData(y) >> self

    def __rshift__(self,y):
        """Right binary shift: x.__rshift__(y) <==> x>>y
        @rtype: Data
        """
        return _tdi.SHIFT_RIGHT(self,makeData(y)).evaluate()

    def __rsub__(self,y):
        """Reverse subtract: x.__rsub__(y) <==> y-x
        @rtype: Data"""
        return makeData(y)-self

    def __rxor__(self,y):
        """Reverse xor: x.__rxor__(y) <==> y^x
        @rtype: Data"""
        return makeData(y)^x

    def __sub__(self,y):
        """Subtract: x.__sub__(y) <==> x-y
        @rtype: Data"""
        return _tdi.SUBTRACT(self,makeData(y)).evaluate()

    def __xor__(self,y):
        """Xor: x.__xor__(y) <==> x^y
        @rtype: Data"""
        return _tdi.IEOR(self,makeData(y)).evaluate()
    
    def compare(self,value):
        """Compare this data with argument
        @param value: data to compare to
        @type value: Data
        @return: Return True if the value and this Data object contain the same data
        @rtype: Bool
        """
        status = _MdsShr.MdsCompareXd(_C.pointer(self.descriptor),_C.pointer(makeData(value).descriptor))
        return (status & 1)==1

    def compile(expr, *args):
        """Static method (routine in C++) which compiles the expression
        and returns the object instance correspondind to the compiled expression.
        @rtype: Data
        """
        return _tdi.COMPILE(expr,*args).evaluate()
    compile=staticmethod(compile)

    def execute(expr,*args):
        """Execute and expression inserting optional arguments into the expression before evaluating
        @rtype: Data"""
        return _tdi.EXECUTE(expr,*args).evaluate()
    execute=staticmethod(execute)

    def setTdiVar(self,tdivarname):
        """Set tdi public variable with this data
        @param tdivarname: The name of the public tdi variable to create
        @type tdivarname: string
        @rtype: Data
        @return: Returns new value of the tdi variable
        """
        return _tdi.EQUALS(_tdi.PUBLIC(tdivarname),self).evaluate()

    def getTdiVar(tdivarname):
        """Get value of tdi public variable
        @param tdivarname: The name of the publi tdi variable
        @type tdivarname: string
        @rtype: Data"""
        try:
            return _tdi.PUBLIC(tdivarname).evaluate()
        except:
            return None
    getTdiVar=staticmethod(getTdiVar)
    
    def decompile(self):
        """Return string representation
        @rtype: string
        """
        return _tdi.DECOMPILE(self).evaluate()

    def __str__(self):
        """String: x.__str__() <==> str(x)
        @type: str"""
        return str(self.decompile())

    __repr__=__str__
    """Representation"""


    def data(self):
        """Return primitimive value of the data.
        @rtype: Scalar,Array
        """
        return _tdi.DATA(self).evaluate().value

    def _getDescrPtr(self):
        """Return pointer to descriptor of inself as an int
        @rtype: int
        """
        d=self.descriptor
        return (_C.addressof(d),d)
    descrPtr=property(_getDescrPtr)

    def evaluate(self):
        """Return the result of TDI evaluate(this).
        @rtype: Data
        """
        return _tdi.EVALUATE(self).evaluate()

    def _isScalar(x):
        """Is item a Scalar
        @rtype: Bool"""
        return isinstance(x,Scalar) and not isinstance(x,Array)
    _isScalar=staticmethod(_isScalar)
    
    def getByte(self):
        """Convert this data into a byte. Implemented at this class level by returning TDI
        data(BYTE(this)). If data() fails or the returned class is not scalar,
        generate an exception.
        @rtype: Int8
        @raise TypeError: Raised if data is not a scalar value
        """
        ans=_tdi.BYTE(self).evaluate()
        if not Data._isScalar(ans):
            raise TypeError('Value not a scalar, %s' % str(type(self)))
        return ans

    def getShort(self):
        """Convert this data into a short. Implemented at this class level by returning TDI
        data(WORD(this)).If data() fails or the returned class is not scalar, generate
        an exception.
        @rtype: Int16
        @raise TypeError: Raised if data is not a scalar value
        """
        ans=_tdi.WORD(self).evaluate()
        if not Data._isScalar(ans):
            raise TypeError('Value not a scalar, %s' % str(type(self)))
        return ans
    
    def getInt(self):
        """Convert this data into a int. Implemented at this class level by returning TDI
        data(LONG(this)).If data() fails or the returned class is not scalar, generate
        an exception.
        @rtype: Int32
        @raise TypeError: Raised if data is not a scalar value
        """
        ans=_tdi.LONG(self).evaluate()
        if not Data._isScalar(ans):
            raise TypeError('Value not a scalar, %s' % str(type(self)))
        return ans

    def getLong(self):
        """Convert this data into a long. Implemented at this class level by returning TDI
        data(QUADWORD(this)).If data() fails or the returned class is not scalar,
        generate an exception.
        @rtype: Int64
        @raise TypeError: if data is not a scalar value
        """
        ans=_tdi.QUADWORD(self).evaluate()
        if not Data._isScalar(ans):
            raise TypeError('Value not a scalar, %s' % str(type(self)))
        return ans

    def getFloat(self):
        """Convert this data into a float32. Implemented at this class level by returning TDI
        data(F_FLOAT(this)).If data() fails or the returned class is not scalar,
        generate an exception.
        @rtype: Float32
        @raise TypeError: Raised if data is not a scalar value
        """
        ans=_tdi.FLOAT(self).evaluate()
        if not Data._isScalar(ans):
            raise TypeError('Value not a scalar, %s' % str(type(self)))
        return ans

    def getDouble(self):
        """Convert this data into a float64. Implemented at this class level by returning TDI
        data(FT_FLOAT(this)). If data() fails or the returned class is not scalar,
        generate an exception.
        @rtype: Float64
        @raise TypeError: Raised if data is not a scalar value
        """
        ans=_tdi.FT_FLOAT(self).evaluate()
        if not Data._isScalar(ans):
            raise TypeError('Value not a scalar, %s' % str(type(self)))
        return ans

    def getFloatArray(self):
        """Convert this data into a float32. Implemented at this class level by returning TDI
        data(F_FLOAT(this)).If data() fails or the returned class is not Array,
        generate an exception.
        @rtype: Float32
        """
        ans=_tdi.FS_FLOAT(self).evaluate()
        if not isinstance(ans,Array):
            raise TypeError('Value is not an array, %s' % (str(type(self)),))
        return ans

    def getDoubleArray(self):
        """Convert this data into a float64. Implemented at this class level by returning TDI
        data(FT_FLOAT(this)). If data() fails or the returned class is not scalar,
        generate an exception.
        @rtype: Float64
        """
        ans=_tdi.FT_FLOAT(self).evaluate()
        if not isinstance(ans,Array):
            raise TypeError('Value is not an array, %s' % (str(type(self)),))
        return ans

    def getShape(self):
        """Get the array dimensions as an integer array. It is implemented at this class
        level by computing TDI expression SHAPE(this). If shape fails an exception is
        generated.
        @rtype: Int32Array
        """
        return _tdi.SHAPE(self).evaluate()

    def getByteArray(self):
        """Convert this data into a byte array. Implemented at this class level by
        returning TDI data(BYTE(this)). If data() fails or the returned class is not
        array, generates an exception. In Java and C++ will return a 1 dimensional
        array using row-first ordering if a multidimensional array.
        @rtype: Int8Array
        """
        ans=_tdi.BYTE(self).evaluate()
        if not isinstance(ans,Array):
            raise TypeError('Value is not an array, %s' % (str(type(self)),))
        return ans

    def getShortArray(self):
        """Convert this data into a short array. Implemented at this class level by
        returning TDI data(WORD(this)). If data() fails or the returned class is not
        array, generates an exception. In Java and C++ will return a 1 dimensional
        array using row-first ordering if a multidimensional array.
        @rtype: Int16Array
        """
        ans = _tdi.WORD(self).evaluate()
        if not isinstance(ans,Array):
            raise TypeError('Value is not an array, %s' % (str(type(self)),))
        return ans

    def getIntArray(self):
        """Convert this data into a int array. Implemented at this class level by
        returning TDI data (LONG(this)). If data() fails or the returned class is not
        array, generates an exception. In Java and C++ will return a 1 dimensional
        array using row-first ordering if a multidimensional array.
        @rtype: Int32Array
        """
        ans = _tdi.LONG(self).evaluate()
        if not isinstance(ans,Array):
            raise TypeError('Value is not an array, %s' % (str(type(self)),))
        return ans

    def getLongArray(self):
        """Convert this data into a long array. Implemented at this class level by
        returning TDI data(QUADWORD(this)). If data() fails or the returned class is
        not array, generates an exception. In Java and C++ will return a 1 dimensional
        array using row-first ordering if a multidimensional array.
        @rtype: Int64Array
        """
        ans=_tdi.QUADWORD(self).evaluate()
        if not isinstance(ans,Array):
            raise TypeError('Value is not an array, %s' % (str(type(self)),))
        return ans

    def getString(self):
        """Convert this data into a STRING. Implemented at this class level by returning
        TDI data((this)). If data() fails or the returned class is not string,
        generates an exception.
        @rtype: String
        """
        return str(_tdi.TEXT(self).evaluate())

    def getUnits(self):
        """Return the TDI evaluation of UNITS_OF(this). EmptyData is returned if no units
        defined.
        @rtype: Data
        """
        return self.units

    def getHelp(self):
        """Returns the result of TDI GET_HELP(this). Returns EmptyData if no help field
        defined.
        @rtype: Data
        """
        return self.help

    def getError(self):
        """Get the error field. Returns EmptyData if no error defined.
        @rtype: Data
        """
        return self.error

    def hasNodeReference(self):
        """Return True if data item contains a tree reference
        @rtype: Bool
        """
        if isinstance(self,_tree.TreeNode) or isinstance(self,_tree.TreePath):
            return True
        elif isinstance(self,Compound):
            for arg in self.args:
                if isinstance(arg,Data) and arg.hasNodeReference():
                    return True
        elif isinstance(self,Apd):
            for arg in self.getDescs():
                if isinstance(arg,Data) and arg.hasNodeReference():
                    return True
        return False

    def setUnits(self,units):
        """Set units
        @rtype: original type
        """
        self.units=units
        return self

    def setHelp(self,help):
        """Set the Help  field for this Data instance.
        @rtype: original type
        """
        self.help=help
        return self

    def setError(self,error):
        """Set the Error field for this Data instance.
        @rtype: original type
        """
        self.error=error
        return self

    def mayHaveChanged(self):
        """return true if the represented data could have been changed since the last time
        this method has been called.
        @rtype: Bool
        """
        return True

    def plot(self,title='',scope=None,row=1,col=1):
        """Plot this data item
        @param title: Title of Scope. Used if scope argument is not provided
        @type title: str
        @param scope: Optional Scope object if adding this to an existing Scope
        @type scope: Scope
        @param row: Row in existing Scope to plot this data
        @type row: int
        @param col: Column in existing Scope
        @type col: int
        @rtype: None
        """
        if scope is None:
            scope=_scope.Scope(title)
        scope.plot(self,self.dim_of(0),row,col)
        scope.show()

    def sind(self):
        """Return sin() of data assuming data is in degrees
        @rtype: Float32Array
        """
        return _tdi.SIND(self).evaluate()

    def serialize(self):
        """Return Uint8Array binary representation.
        @rtype: Uint8Array
        """
        xd=_Descriptor_xd()
        status = _MdsShr.MdsSerializeDscOut(_C.pointer(self.descriptor),_C.pointer(xd))
        if (status & 1)==1:
          return Uint8Array(xd.value)
        else:
          raise TdiException("Error serializing data: %s" % getStatusMsg(status))

    def deserialize(data):
        """Return Data from serialized buffer.
        @param data: Buffer returned from serialize.
        @type data: Uint8Array
        @rtype: Data
        """
        data=Uint8Array(data)
        xd=_Descriptor_xd()
        status = _MdsShr.MdsSerializeDscIn(data.value.ctypes.data,_C.pointer(xd))
        if (status & 1)==1:
          return xd.value
        else:
          raise TdiException("Error deserializing data: %s" % getStatusMsg(status))
    deserialize=staticmethod(deserialize)

    def makeData(value):
        """Return MDSplus data class from value.
        @param value: Any value
        @type data: Any
        @rtype: Data
        """
        return makeData(value)
    makeData=staticmethod(makeData)

class EmptyData(Data):
    """No Value"""
    def __init__(self):
        pass

    def __or__(self,y):
      return y
    
    def __str__(self):
        return "*"

    def _getValue(self):
       return None

    def _getDescriptor(self):
      d=_Descriptor()
      d.dclass=1
      d.dtype=24
      d.length=0
      d.pointer=0
      return _descrWithUnitsAndError(self,d)
    descriptor=property(_getDescriptor,)

    value=property(_getValue)

    pass

def makeScalar(value):
  """If possible, convert the argument to an MDSplus Scalar.
  @param value: Any value
  @type data: Any
  @rtype: Scalar
  """
  if isinstance(value,str):
    return String(value)
  if isinstance(value,Scalar):
    return _copy.deepcopy(value)
  if isinstance(value,_NP.generic):
    if isinstance(value,_NP.string_):
      return String(value)
    try:
      if isinstance(value,_NP.bytes_):
        return String(str(value,encoding='utf8'))
    except:
      pass
    if isinstance(value,_NP.bool_):
      return Uint8(int(value))
    return Scalar.numpyToClass[type(value).__name__](value)
  if isinstance(value,_C._SimpleCData) and type(value).__name__ in Scalar.ctypesToClass:
    klass=Scalar.ctypesToClass[type(value).__name__]
    return klass(klass.dtype_numpy(value.value))
  try:
    if isinstance(value,_C.c_bool):
      return Uint8(value.value)
  except:
    pass
  if isinstance(value,int):
    info=_NP.iinfo(_NP.int32)
    if value >= info.min and value <= info.max:
      return Int32(_NP.int32(value))
    else:
      return Int64(_NP.int64(value))
  try:
    if isinstance(value,long):
      info=_NP.iinfo(_NP.int32)
      if value >= info.min and value <= info.max:
        return Int32(_NP.int32(value))
      else:
        return Int64(_NP.int64(value))
  except:
    pass
  if isinstance(value,float):
    info=_NP.finfo(_NP.float32)
    if value >= info.min and value <= info.max:
      return Float32(value)
    else:
      return Float64(value)
  if isinstance(value,str):
    return String(value)
  if isinstance(value,bytes):
    return String(value.decode())
  if isinstance(value,bool):
    return Uint8(int(value))
  if isinstance(value,complex):
    info=_NP.finfo(_NP.float32)
    if value.real >= info.min and value <= info.max:
      return Complex64(_NP.complex64(value))
    else:
      return Complex128(_NP.complex128(value))
  if isinstance(value,_NP.complex64):
    return Complex64(value)
  if isinstance(value,_NP.complex128):
    return Complex128(value)
  raise TypeError('Cannot make Scalar out of '+str(type(value)))

def pointerToObject(pointer):
  if pointer == 0:
    return None
  else:
    print "In pointerToObject py code - pointer=%s" % (str(pointer),)
    ans = _C.cast(pointer,_C.POINTER(_Descriptor)).contents.value
    print "pointerToObject Got %s" % (str(ans),)
    return ans

class Scalar(Data):
  dtype_mds=None
  mdsclass=1
  numpyToClass=dict()
  ctypesToClass=dict()
  mdsdtypeToClass=dict()
   
  def __new__(cls,value=0):
    if 'Array' not in cls.__name__:
      try:
        if (isinstance(value,Array)) or isinstance(value,list) or isinstance(value,_NP.ndarray):
          return globals()[cls.__name__+'Array'](value)
      except:
        pass

    return super(Scalar,cls).__new__(cls)
        
  def __init__(self,value=0):
    if self.__class__.__name__ == 'Scalar':
      raise TypeError("cannot create 'Scalar' instances")
    if isinstance(value,Scalar):
      value=value._value
    self._value=self.dtype_numpy(value)

  def __getattr__(self,name):
    return self._value.__getattribute__(name)

  def _getValue(self):
    """Return the numpy scalar representation of the scalar"""
    return self._value
  value=property(_getValue)
            
  def _getDescriptor(self):
    """Return a MDSplus descriptor"""
    d=_Descriptor()
    d.length=self.itemsize
    d.dtype=self.dtype_mds
    d.dclass=self.mdsclass
    if isinstance(self,String):
      d.pointer=_C.cast(self.dtype_ctypes(self.value),_C.c_void_p)
    elif isinstance(self,(Complex64,Complex128)):
      value=_NP.array([self._value.real,self._value.imag])
      if hasattr(self,'dtype_cvt'):
        pointer=_C.cast(value.ctypes.data,_C.c_void_p)
        _TdiShr.CvtConvertFloat(pointer,_C.c_int32(self.dtype_cvt),pointer,_C.c_int32(self.dtype_mds))
      else:
        pointer=_C.cast(value.ctypes.data,_C.c_void_p)
      d.original=(self,value)
      d.pointer=pointer
    else:
      if hasattr(self,'dtype_cvt'):
        tmp_value=_copy.copy(self.value)
        pointer=_C.cast(_C.pointer(self.dtype_ctypes(tmp_value)),_C.c_void_p)
        _TdiShr.CvtConvertFloat(pointer,_C.c_int32(self.dtype_cvt),pointer,_C.c_int32(self.dtype_mds))
        d.original=(self,tmp_value)
      else:
        pointer=_C.cast(_C.pointer(self.dtype_ctypes(self.value)),_C.c_void_p)
        d.original=self
      d.pointer=pointer
    return _descrWithUnitsAndError(self,d)
  descriptor=property(_getDescriptor)

  def __str__(self):
    if _NP.isnan(self.value):
      return '$ROPRAND'
    else:
      POSTFIX={_NP.uint8:'BU',_NP.uint16:'WU',_NP.uint32:'LU',_NP.uint64:'QU',
               _NP.int8:'B',_NP.int16:'W',_NP.int64:'Q'}
      if type(self.value) in POSTFIX:
        postfix=POSTFIX[type(self.value)]
      else:
        postfix=''
      return self._decompile_units_and_error(str(self.value)+postfix)

  def decompile(self):
    return String(str(self))

#  def __int__(self):
#    """Integer: x.__int__() <==> int(x)
#    @rtype: int"""
#    return self._value.__int__()

  def __long__(self):
    """Long: x.__long__() <==> long(x)
    @rtype: int"""
    return self.__value.__long__()

  def _unop(self,op):
    return makeData(getattr(self.value,op)())

  def _binop(self,op,y):
    try:
      y=y.value
    except AttributeError:
      pass
    ans=getattr(self.value,op)(y)
    return makeData(ans)

  def _triop(self,op,y,z):
    try:
      y=y.value
    except AttributeError:
      pass
    try:
      z=z.value
    except AttributeError:
      pass
    return makeData(getattr(self.value,op)(y,z))

  def all(self):
    return self._unop('all')

  def any(self):
    return self._unop('any')

  def argmax(self,*axis):
    if axis:
      return self._binop('argmax',axis[0])
    else:
      return self._unop('argmax')

  def argmin(self,*axis):
    if axis:
      return self._binop('argmin',axis[0])
    else:
      return self._unop('argmin')

  def argsort(self,axis=-1,kind='quicksort',order=None):
    return makeData(self.value.argsort(axis,kind,order))

  def astype(self,type):
    return makeData(self.value.astype(type))

  def byteswap(self):
    return self._unop('byteswap')

  def clip(self,y,z):
    return self._triop('clip',y,z)

  def _dataFromDescriptor(desc):
    if desc.pointer == _C.c_void_p(0):
      ans = None
    elif desc.dtype == 0:
      ans = EmptyData()
    elif desc.dtype in Scalar.mdsdtypeToClass:
      klass=Scalar.mdsdtypeToClass[desc.dtype]
      if debug:
        print "Got a class: %s" % (str(klass),)
      if hasattr(klass,'dtype_cvt'):
        _TdiShr.CvtConvertFloat(desc.pointer,_C.c_int32(klass.dtype_mds),desc.pointer,_C.c_int32(klass.dtype_cvt))
      if issubclass(klass,String):
        if desc.length == 0:
          ans = klass('')
        else:
          if debug:
            print "desc length=%d" % (desc.length,)
            print "got: %s" % (str(_NP.array(_C.cast(desc.pointer,_C.POINTER((_C.c_byte*desc.length))).contents[:],dtype=_NP.uint8).tostring().decode()),)
          ans=klass(str(_NP.array(_C.cast(desc.pointer,_C.POINTER((_C.c_byte*desc.length))).contents[:],dtype=_NP.uint8).tostring().decode()))
          if debug:
            print "ans=%s" % (str(ans),)
      elif issubclass(klass,(Complex64,Complex128)):
        ans=_C.cast(desc.pointer,_C.POINTER((klass.dtype_ctypes))).contents
        ans=klass(klass.dtype_numpy(complex(ans[0],ans[1])))
      else:
        ans=klass(klass.dtype_numpy(_C.cast(desc.pointer,_C.POINTER(klass.dtype_ctypes)).contents.value))
    elif desc.dtype in _tree.TreeNode.mdsdtypeToClass:
      ans=_tree.TreeNode._dataFromDescriptor(desc)
    else:
      raise Exception("Unsupported dtype: %d" % desc.dtype)
    return ans
  _dataFromDescriptor=staticmethod(_dataFromDescriptor)

Data.mdsclassToClass[Scalar.mdsclass]=Scalar


def _scalar_decorator(klass):
  if klass.dtype_numpy.__name__ not in klass.numpyToClass:
    klass.numpyToClass[klass.dtype_numpy.__name__]=klass
  klass.mdsdtypeToClass[klass.dtype_mds]=klass
  if klass.dtype_ctypes.__name__ not in klass.ctypesToClass:
    klass.ctypesToClass[klass.dtype_ctypes.__name__]=klass
  return klass

#@_scalar_decorator
class Int8(Scalar):
  """8-bit signed number"""
  dtype_mds=6
  dtype_numpy=_NP.int8
  dtype_ctypes=_C.c_byte
Int8=_scalar_decorator(Int8)

#@_scalar_decorator
class Int16(Scalar):
  """16-bit signed number"""
  dtype_mds=7
  dtype_numpy=_NP.int16
  dtype_ctypes=_C.c_int16
Int16=_scalar_decorator(Int16)

#@_scalar_decorator
class Int32(Scalar):
  """32-bit signed number"""
  dtype_mds=8
  dtype_numpy=_NP.int32
  dtype_ctypes=_C.c_int32
Int32=_scalar_decorator(Int32)

#@_scalar_decorator
class Int64(Scalar):
  """64-bit signed number"""
  dtype_mds=9
  dtype_numpy=_NP.int64
  dtype_ctypes=_C.c_int64
Int64=_scalar_decorator(Int64)

#@_scalar_decorator
class Uint8(Scalar):
  """8-bit unsigned number"""
  dtype_mds=2
  dtype_numpy=_NP.uint8
  dtype_ctypes=_C.c_uint8
Uint8=_scalar_decorator(Uint8)

#@_scalar_decorator
class Uint16(Scalar):
  """16-bit unsigned number"""
  dtype_mds=3
  dtype_numpy=_NP.uint16
  dtype_ctypes=_C.c_uint16
Uint16=_scalar_decorator(Uint16)

#@_scalar_decorator
class Uint32(Scalar):
  """32-bit unsigned number"""
  dtype_mds=4
  dtype_numpy=_NP.uint32
  dtype_ctypes=_C.c_uint32
Uint32=_scalar_decorator(Uint32)

#@_scalar_decorator
class Uint64(Scalar):
  """64-bit unsigned number"""
  dtype_mds=5
  dtype_numpy=_NP.uint64
  dtype_ctypes=_C.c_uint64
  def _getDate(self):
    return _tdi.DATE_TIME(self).evaluate()
  date=property(_getDate)
Uint64=_scalar_decorator(Uint64)

#@_scalar_decorator
class Float32(Scalar):
  """32-bit floating point number"""
  dtype_mds=52
  dtype_numpy=_NP.float32
  dtype_ctypes=_C.c_float
Float32=_scalar_decorator(Float32)

#@_scalar_decorator
class Complex64(Scalar):
  """32-bit complex number"""
  dtype_mds=54
  dtype_numpy=_NP.complex64
  dtype_ctypes=_C.c_float*2
  def __str__(self):
    return "Cmplx(%g,%g)" % (self._value.real,self._value.imag)
Complex64=_scalar_decorator(Complex64)

#@_scalar_decorator
class Float64(Scalar):
  """64-bit floating point number"""
  dtype_mds=53
  dtype_numpy=_NP.float64
  dtype_ctypes=_C.c_double
  def __str__(self):
    return ("%E" % self._value).replace("E","D")
Float64=_scalar_decorator(Float64)

#@_scalar_decorator
class Complex128(Scalar):
  dtype_mds=55
  dtype_numpy=_NP.complex128
  dtype_ctypes=_C.c_double*2
  """64-bit complex number"""
  def __str__(self):
    return "Cmplx(%s,%s)" % (str(Float64(self._value.real)),str(Float64(self._value.imag)))
Complex128=_scalar_decorator(Complex128)

#@_scalar_decorator
class String(Scalar):
  """String"""
  dtype_mds=14
  dtype_numpy=_NP.string_
  dtype_ctypes=_C.c_char_p
  def __radd__(self,y):
    """Reverse add: x.__radd__(y) <==> y+x
    @rtype: Data"""
    return self.execute('$//$',y,self)
  def __add__(self,y):
    """Add: x.__add__(y) <==> x+y
    @rtype: Data"""
    return self.execute('$//$',self,y)
  def __str__(self):
    """String: x.__str__() <==> str(x)
    @rtype: String"""
    if len(self._value) > 0:
      ans = str(self.value.tostring().decode())
    else:
      ans = ''
    return self._decompile_units_and_error(ans,True)

  def __len__(self):
    return len(str(self))

  def decompile(self):
    return String(repr(self))

  def __repr__(self):
    return repr(str(self))

  def __getitem__(self,y):
    return String(self.value[y])
String=_scalar_decorator(String)

#@_scalar_decorator
class FFloat32(Float32):
  """VMS F_FLOAT 32-bit floating point number"""
  dtype_mds=10
  dtype_cvt=Float32.dtype_mds
FFloat32=_scalar_decorator(FFloat32)

#@_scalar_decorator
class DFloat64(Float64):
  """VMS D_FLOAT 64-bit floating point number"""
  dtype_mds=11
  dtype_cvt=Float64.dtype_mds
DFloat64=_scalar_decorator(DFloat64)

#@_scalar_decorator
class GFloat64(Float64):
  """VMS G_FLOAT 64-bit floating point number"""
  dtype_mds=27
  dtype_cvt=Float64.dtype_mds
GFloat64=_scalar_decorator(GFloat64)

#@_scalar_decorator
class FComplex64(Complex64):
  """VMS F_COMPLEX 32-bit complex number"""
  dtype_mds=12
  dtype_cvt=Complex64.dtype_mds
FComplex64=_scalar_decorator(FComplex64)

#@_scalar_decorator
class DComplex128(Complex128):
  """VMS D_COMPLEX 64-bit complex number"""
  dtype_mds=13
  dtype_cvt=Complex128.dtype_mds
DComplex128=_scalar_decorator(DComplex128)

#@_scalar_decorator
class GComplex128(Complex128):
  """VMS G_COMPLEX 64-bit complex number"""
  dtype_mds=29
  dtype_cvt=Complex128.dtype_mds
GComplex128=_scalar_decorator(GComplex128)

#@_scalar_decorator
class Ident(String):
  """TDI Variable reference"""
  dtype_mds=191
  dtype_numpy=_NP.string_
  dtype_ctypes=_C.c_char_p
  def data(self):
    return self.evaluate().data()
  def evaluate(self):
    return TdiEvaluate(self)
Ident=_scalar_decorator(Ident)

#class Int128(Scalar):
#    """128-bit number"""
#    def __init__(self):
#        raise TypeError("Int128 is not yet supported")
#
#class Uint128(Scalar):
#    """128-bit unsigned number"""
#    def __init__(self):
#        raise TypeError("Uint128 is not yet supported")


def makeArray(value):
    if isinstance(value,Array):
        return value
    if isinstance(value,Scalar):
        return makeArray((value._value,))
    if isinstance(value,_C.Array):
        try:
            return makeArray(_NP.ctypeslib.as_array(value))
        except Exception:
            pass
    if isinstance(value,tuple) | isinstance(value,list):
        try:
            ans=_NP.array(value)
            if str(ans.dtype)[1:2]=='U':
              ans=ans.astype('S')
            return makeArray(ans)
        except ValueError:
            newlist=list()
            for i in value:
                newlist.append(makeData(i).data())
            return makeArray(_NP.array(newlist))
    if isinstance(value,_NP.ndarray):
        if str(value.dtype)[0:2] == '|S':
            return StringArray(value)
        if str(value.dtype) == 'bool':
            return makeArray(_NP.array(value,dtype=_NP.uint8))
        if str(value.dtype) == 'object':
            raise TypeError('cannot make Array out of an _NP.ndarray of dtype object')
        return Array.numpyToClass[value.dtype.type.__name__](value)
    if isinstance(value,(_NP.generic,int,float,str,bool)):
        return makeArray(_NP.array(value).reshape(1))
    try:
      if isinstance(value,long):
        return makeArray(_NP.array(value).reshape(1))
    except:
      pass
    raise TypeError('Cannot make Array out of '+str(type(value)))
                        


class Array(Data):
    mdsclass=4
    numpyToClass=dict()
    mdsdtypeToClass=dict()
    ctypesToClass=dict()
    
    def __init__(self,value=0):
        if self.__class__.__name__ == 'Array':
            raise TypeError("cannot create 'Array' instances")
        if isinstance(value,_C.Array):
            try:
                value=_NP.ctypeslib.as_array(value)
            except Exception:
                pass
        self._value=_NP.array(value,dtype=self.dtype_numpy)
        return
    
    def __getattr__(self,name):
        return self._value.__getattribute__(name)

    def _getValue(self):
        """Return the numpy ndarray representation of the array"""
        return self._value

    value=property(_getValue)

    
    def _unop(self,op):
        return makeData(getattr(self._value,op)())

    def _binop(self,op,y):
        try:
            y=y._value
        except AttributeError:
            pass
        return makeData(getattr(self._value,op)(y))

    def _triop(self,op,y,z):
        try:
            y=y._value
        except AttributeError:
            pass
        try:
            z=z._value
        except AttributeError:
            pass
        return makeData(getattr(self._value,op)(y,z))
    
    def __array__(self):
        raise TypeError('__array__ not yet supported')

    def __copy__(self):
        return type(self)(self._value)

    def __deepcopy__(self,memo=None):
        return self.__copy__()

    def getElementAt(self,itm):
        return makeData(self._value[itm])

    def setElementAt(self,i,y):
        self._value[i]=y
    
    def all(self):
        return self._unop('all')

    def any(self):
        return self._unop('any')

    def argmax(self,*axis):
        if axis:
            return self._binop('argmax',axis[0])
        else:
            return self._unop('argmax')

    def argmin(self,*axis):
        if axis:
            return self._binop('argmin',axis[0])
        else:
            return self._unop('argmin')

    def argsort(self,axis=-1,kind='quicksort',order=None):
        return makeData(self._value.argsort(axis,kind,order))

    def astype(self,type):
        return makeData(self._value.astype(type))

    def byteswap(self):
        return self._unop('byteswap')

    def clip(self,y,z):
        return self._triop('clip',y,z)


    def decompile(self):
        def arrayDecompile(a,cl):
            ans='['
            if len(a.shape)==1:
                for idx in range(len(a)):
                    sval=cl(a[idx])
                    if idx < len(a)-1:
                        ending=','
                    else:
                        ending=']'
                    ans=ans+sval.__repr__()+ending
                return ans
            else:
                for idx in range(a.shape[0]):
                    if idx < a.shape[0]-1:
                        ending=', '
                    else:
                        ending=']'
                    ans=ans+arrayDecompile(a[idx],cl)+ending
                return ans
        if len(self._value) < 500:
          ans=arrayDecompile(self._value,self.__class__.__bases__[1])
        else:
          ans='%s /*** etc. ***/' % self._value.flat[0]
        if hasattr(self,'bounds'):
          tmp='Set_Range('
          for i in range(0,len(self.bounds),2):
            tmp+='%d:%d,'% (self.bounds[i],self.bounds[i+1])
          ans=tmp+ans+')'
        elif len(self._value) > 500:
          tmp='Set_Range('
          for i in range(0,len(self.value.shape)):
            tmp+='%d,' % self.value.shape[i]
          ans=tmp+ans+')'
        return self._decompile_units_and_error(ans)

    def __str__(self):
      return str(self.decompile())

    def _getDescriptor(self):
      """Return a MDSplus descriptor"""
      d=_Descriptor_a()
      d.length=self.itemsize
      d.dtype=self.dtype_mds
      d.dclass=self.mdsclass
      d.scale=0
      d.digits=0
      d.aflags=0
      d.dimct=len(self.value.shape)
      d.arsize=self.value.nbytes
      if d.dimct > 1 or hasattr(self,'bounds'):
        d.coeff=1
        for i in range(d.dimct):
          d.coeff_and_bounds[i]=self.value.shape[i]
      if hasattr(self,'bounds'):
        d.bounds=1
        for i in range(len(self.bounds)):
          d.coeff_and_bounds[d.dimct+i]=self.bounds[i]
      if hasattr(self,'dtype_cvt'):
        tmp_value=_copy.copy(self.value)
        d.pointer=d.a0=tmp_value.ctypes.data
        ptr=_copy.copy(d.pointer)
        for i in range(d.arsize/d.length):
          _TdiShr.CvtConvertFloat(ptr,_C.c_int32(self.dtype_cvt),ptr,_C.c_int32(self.dtype_mds))
          ptr=ptr+d.length
        d.original=(self,tmp_value)
      else:
        d.pointer=d.a0=self.value.ctypes.data
        d.original=(self)
      return _descrWithUnitsAndError(self,d)
    descriptor=property(_getDescriptor)

    def __setattr__(self,name,value):
      if name == 'bounds':
        self.__dict__['bounds']=value
      else:
        super(Array,self).__setattr__(name,value)

    def _dataFromDescriptor(desc):
      desc=_C.cast(_C.pointer(desc),_C.POINTER(_Descriptor_a)).contents
      if desc.dtype == 0:
        desc.dtype = Int32.dtype_mds
      if desc.coeff:
        desc.arsize=desc.length
        shape=list()
        for i in range(desc.dimct):
          dim=desc.coeff_and_bounds[desc.dimct-i-1]
          if dim > 0:
            desc.arsize=desc.arsize*dim
            shape.append(dim)
      else:
        shape=[int(desc.arsize/desc.length),]
      if desc.dtype == _tree.TreeNode.dtype_mds:
        nids=Int32Array(_NP.ndarray(shape=shape,dtype=Int32.dtype_ctypes,
                        buffer=buffer(_C.cast(desc.pointer,_C.POINTER(Int32.dtype_ctypes * int(desc.arsize/desc.length))).contents)))
        ans=_tree.TreeNodeArray(nids)
      elif desc.dtype in Array.mdsdtypeToClass:
        klass=Array.mdsdtypeToClass[desc.dtype]
        if hasattr(klass,'dtype_cvt'):
          ptr=_copy.copy(desc.pointer)
          for i in range(desc.arsize/desc.length):
            _TdiShr.CvtConvertFloat(ptr,_C.c_int32(klass.dtype_mds),ptr,_C.c_int32(klass.dtype_cvt))
            ptr=ptr+desc.length
        if issubclass(klass,StringArray):
          ans=klass(_NP.ndarray(shape=shape,dtype=_NP.dtype(('S',desc.length)),buffer=buffer(_C.cast(desc.pointer,_C.POINTER(_C.c_byte*desc.arsize)).contents)))
        elif issubclass(klass,(Complex64Array,Complex128Array)):
          ans=klass(_NP.ndarray(shape=shape,
                                  dtype=klass.dtype_numpy,
                                  buffer=buffer(_C.cast(desc.pointer,_C.POINTER(klass.dtype_ctypes * int(desc.arsize*2/desc.length))).contents)))
        else:
          ans=klass(_NP.ndarray(shape=shape,dtype=klass.dtype_ctypes,
                        buffer=buffer(_C.cast(desc.pointer,_C.POINTER(klass.dtype_ctypes * int(desc.arsize/desc.length))).contents)))
        if desc.bounds:
          ans.bounds=desc.coeff_and_bounds[int(desc.dimct) : int(desc.dimct*3)]
      else:
        raise TypeError('Arrays of type %d are unsupported.' % desc.dtype)
      return ans
    _dataFromDescriptor=staticmethod(_dataFromDescriptor)

Data.mdsclassToClass[Array.mdsclass]=Array

def _array_decorator(klass):
  if klass.dtype_numpy not in klass.numpyToClass:
    klass.numpyToClass[klass.dtype_numpy.__name__]=klass
  klass.mdsdtypeToClass[klass.dtype_mds]=klass
  if klass.dtype_ctypes not in klass.ctypesToClass:
    klass.ctypesToClass[klass.dtype_ctypes]=klass
  return klass

#@_array_decorator
class Int8Array(Array,Int8):
    """8-bit signed number"""
Int8Array=_array_decorator(Int8Array)

#@_array_decorator
class Int16Array(Array,Int16):
    """16-bit signed number"""
Int16Array=_array_decorator(Int16Array)

#@_array_decorator
class Int32Array(Array,Int32):
    """32-bit signed number"""
Int32Array=_array_decorator(Int32Array)

#@_array_decorator
class Int64Array(Array,Int64):
    """64-bit signed number"""
Int64Array=_array_decorator(Int64Array)

#@_array_decorator
class Uint8Array(Array,Uint8):
    """8-bit unsigned number"""

    def deserialize(self):
        """Return data item if this array was returned from serialize.
        @rtype: Data
        """
        return Data.deserialize(self)
Uint8Array=_array_decorator(Uint8Array)

#@_array_decorator
class Uint16Array(Array,Uint16):
    """16-bit unsigned number"""
Uint16Array=_array_decorator(Uint16Array)

#@_array_decorator
class Uint32Array(Array,Uint32):
    """32-bit unsigned number"""
Uint32Array=_array_decorator(Uint32Array)

#@_array_decorator
class Uint64Array(Array,Uint64):
    """64-bit unsigned number"""
Uint64Array=_array_decorator(Uint64Array)

#@_array_decorator
class Float32Array(Array,Float32):
    """32-bit floating point number"""
Float32Array=_array_decorator(Float32Array)

#@_array_decorator
class FFloat32Array(Array,FFloat32):
    """32-bit floating point number"""
FFloat32Array=_array_decorator(FFloat32Array)

#@_array_decorator
class Complex64Array(Array,Complex64):
    """32-bit complex number"""
Complex64Array=_array_decorator(Complex64Array)

#@_array_decorator
class FComplex64Array(Array,FComplex64):
    """VMS F_FLOAT 32-bit complex number"""
FComplex64Array=_array_decorator(FComplex64Array)

#@_array_decorator
class Float64Array(Array,Float64):
    """64-bit floating point number"""
Float64Array=_array_decorator(Float64Array)

#@_array_decorator
class DFloat64Array(Array,DFloat64):
    """VMS D_FLOAT 64-bit floating point number"""
DFloat64Array=_array_decorator(DFloat64Array)

#@_array_decorator
class GFloat64Array(Array,GFloat64):
    """VMS G_FLOAT 64-bit floating point number"""
GFloat64Array=_array_decorator(GFloat64Array)

#@_array_decorator
class Complex128Array(Array,Complex128):
    """64-bit complex number"""
Complex128Array=_array_decorator(Complex128Array)

#@_array_decorator
class DComplex128Array(Array,DComplex128):
    """VMS D_FLOAT 64-bit complex number"""
DComplex128Array=_array_decorator(DComplex128Array)

#@_array_decorator
class GComplex128Array(Array,GComplex128):
    """VMS G_FLOAT 64-bit complex number"""
GComplex128Array=_array_decorator(GComplex128Array)

#@_array_decorator
class StringArray(Array,String):
    """String"""

    def __radd__(self,y):
        """Reverse add: x.__radd__(y) <==> y+x
        @rtype: Data"""
        return self.execute('$//$',y,self)
    def __add__(self,y):
        """Add: x.__add__(y) <==> x+y
        @rtype: Data"""
        return self.execute('$//$',self,y)
    def __str__(self):
        """String: x.__str__() <==> str(x)
        @rtype: String"""
        return str(self.decompile())
StringArray=_array_decorator(StringArray)

#class Int128Array(Array):
#    """128-bit signed number"""
#    def __init__(self):
#        raise TypeError("Int128Array is not yet supported")
#
#class Uint128Array(Array):
#    """128-bit unsigned number"""
#    def __init__(self):
#        raise TypeError("Uint128Array is not yet supported")


class Compound(Data):
    mdsclass=194
    mdsdtypeToClass=dict()

    def __init__(self,*args, **params):
        """MDSplus compound data.
        """
        if self.__class__.__name__=='Compound':
            raise TypeError("Cannot create instances of class Compound")
        if 'args' in params:
            args=params['args']
        if 'params' in params:
            params=params['params']
        if 'opcode' in params:
            self._opcode=params['opcode']
        try:
            self._argOffset=self.argOffset
        except:
            self._argOffset=len(self.fields)
        if isinstance(args,tuple):
            if len(args) > 0:
                if isinstance(args[0],tuple):
                    args=args[0]
        self.args=args
        for keyword in params:
            if keyword in self.fields:
                super(type(self),self).__setitem__(self._fields[keyword],params[keyword])

    def __hasBadTreeReferences__(self,tree):
        for arg in self.args:
            if isinstance(arg,Data) and arg.__hasBadTreeReferences__(tree):
                return True
        return False

    def __fixTreeReferences__(self,tree):
        ans = _copy.deepcopy(self)
        newargs=list(ans.args)
        for idx in range(len(newargs)):
            if isinstance(newargs[idx],Data) and newargs[idx].__hasBadTreeReferences__(tree):
                newargs[idx]=newargs[idx].__fixTreeReferences__(tree)
        ans.args=tuple(newargs)
        return ans
        
    def __getattr__(self,name,*args):
        if name in self.__dict__:
            print "in dict"
            return self.__dict__[name]
        if name == '_opcode_name':
            return 'undefined'
        if name == '_fields':
            return dict()
        if name == 'args':
            try:
                return self.__dict__[name]
            except:
                return None
        if name == '_opcode':
            return None
        if name == '_argOffset':
            return 0
        if name == 'opcode':
            return self._opcode
        if name == 'dtype':
            return self.dtype_mds
        if name == self._opcode_name:
            return self._opcode
        if name in self._fields:
            try:
                return self.args[self._fields[name]]
            except:
                return None
        if name == self.__class__.__name__.lower():
          return self
        raise AttributeError('No such attribute '+str(name))

    def __getitem__(self,num):
        try:
            return self.args[num]
        except:
            return None

    def __setattr__(self,name,value):
        if name == 'opcode':
            self._opcode=value
        if name == 'args':
            if isinstance(value,tuple):
                self.__dict__[name]=value
                return
            else:
                raise TypeError('args attribute must be a tuple')
        if name in self._fields:
            tmp=list(self.args)
            while len(tmp) <= self._fields[name]:
                tmp.append(None)
            tmp[self._fields[name]]=value
            self.args=tuple(tmp)
            return
        if name == self._opcode_name:
            self._opcode=value
            return
        super(Compound,self).__setattr__(name,value)


    def __setitem__(self,num,value):
        if isinstance(num,slice):
            indices=num.indices(num.start+len(value))
            idx=0
            for i in range(indices[0],indices[1],indices[2]):
                self.__setitem__(i,value[idx])
                idx=idx+1
        else:
            try:
                tmp=list(self.args)
            except:
                tmp=list()
            while len(tmp) <= num:
                tmp.append(None)
            tmp[num]=value
            self.args=tuple(tmp)
        return

    def _getDescriptor(self):
      d=_Descriptor_r()
      d.dtype=self.dtype_mds
      d.dclass=self.mdsclass
      if self.opcode is not None:
        d.length=2
        d.pointer=_C.cast(_C.pointer(_C.c_int16(self.opcode)),_C.c_void_p)
      else:
        d.length=0
        d.pointer=0
      d.ndesc=len(self.args)
      d.originals=[self,]
      for i in range(len(self.args)):
        if self.args[i] is not None:
          argd=makeData(self.args[i]).descriptor
          d.dscptrs[i]=_C.cast(_C.pointer(argd),_C.c_void_p)
          d.originals.append(argd)
        else:
          d.dscptrs[i]=_C.c_void_p(0)
      return _descrWithUnitsAndError(self,d)
    descriptor=property(_getDescriptor,)
        
#    def decompile(self):
#        arglist=list()
#        for arg in self.args:
#            arglist.append(makeData(arg).decompile())
#        return 'Build_'+self.__class__.__name__+'('+','.join(arglist)+')'

    def getArgumentAt(self,idx):
        """Return argument at index idx (indexes start at 0)
        @rtype: Data,None
        """
        return Compound.__getitem__(self,idx+self._argOffset)
    
    def getArguments(self):
        """Return arguments
        @rtype: Data,None
        """
        return Compound.__getitem__(self,slice(self._argOffset,None))

    def getDescAt(self,idx):
        """Return descriptor with index idx (first descriptor is 0)
        @rtype: Data
        """
        return Compound.__getitem__(self,idx)

    def getDescs(self):
        """Return descriptors or None if no descriptors
        @rtype: tuple,None
        """
        return self.args

    def getNumDescs(self):
       """Return number of descriptors
       @rtype: int
       """
       try:
           return len(self.args)
       except:
           return 0

    def setArgumentAt(self,idx,value):
        """Set argument at index idx (indexes start at 0)"""
        return Compound.__setitem__(self,idx+self._argOffset,value)

    def setArguments(self,args):
        """Set arguments
        @type args: tuple
        """
        return Compound.__setitem__(self,slice(self._argOffset,None),args)

    def setDescAt(self,n,value):
        """Set descriptor at index idx (indexes start at 0)"""
        return Compound.__setitem__(self,n,value)

    def setDescs(self,args):
        """Set descriptors
        @type args: tuple
        """
        self.args=value

    def _dataFromDescriptor(desc):
      desc=_C.cast(_C.pointer(desc),_C.POINTER(_Descriptor_r)).contents
      if desc.dtype == 211:
        ans=_C.cast(desc.dscptrs[0],_C.POINTER(_Descriptor)).contents.value
        ans._units=_C.cast(desc.dscptrs[1],_C.POINTER(_Descriptor)).contents.value
      elif desc.dtype == 213:
        ans=_C.cast(desc.dscptrs[0],_C.POINTER(_Descriptor)).contents.value
        ans._error=_C.cast(desc.dscptrs[1],_C.POINTER(_Descriptor)).contents.value
      elif desc.dtype in Compound.mdsdtypeToClass:
        klass=Compound.mdsdtypeToClass[desc.dtype]
        args=list()
        for i in range(desc.ndesc):
          if desc.dscptrs[i]:
            value=_C.cast(desc.dscptrs[i],_C.POINTER(_Descriptor)).contents.value
          else:
            value=None
          args.append(value)
        opcode=None
        if (desc.length > 0) and issubclass(klass,_tdi.Builtin):
          if desc.length == 1:
            opcode=_C.cast(desc.pointer,_C.POINTER(_C.c_int8)).contents.value
          elif desc.length == 2:
            opcode=_C.cast(desc.pointer,_C.POINTER(_C.c_int16)).contents.value
          elif desc.length == 4:
            opcode=_C.cast(desc.pointer,_C.PONTER(_C.c_int32)).contents.value
          else:
            raise TdiException('Invalid opcode length: %d' % (desc.length,))
          ans= klass(opcode,tuple(args))
        else:
          ans = klass(tuple(args))
      else:
        raise TdiException('Unknown compound data type: %d' % (desc.dtype,))
      return ans
    _dataFromDescriptor=staticmethod(_dataFromDescriptor)

Data.mdsclassToClass[Compound.mdsclass]=Compound
        
class _compoundMeta(type):

    def __new__(meta,classname,bases,classDict):
        if len(classDict)==0:
            classDict=dict(bases[0].__dict__)
            newClassDict=classDict
            newClassDict['_fields']=dict()
            idx=0
            for f in classDict['fields']:
                name=f[0:1].upper()+f[1:]
                exec ("def get"+name+"(self): return self.__getattr__('"+f+"')")
                exec ("newClassDict['get'+name]=get"+name)
                newClassDict['get'+name].__doc__='Get the '+f+' field\n@rtype: Data'
                exec ('def set'+name+'(self,value): return self.__setattr__("'+f+'",value)')
                exec ("newClassDict['set'+name]=set"+name)
                newClassDict['set'+name].__doc__='Set the '+f+' field\n@type value: Data\n@rtype: None'
                newClassDict['_fields'][f]=idx
                idx=idx+1
                c=type.__new__(meta,classname,bases,newClassDict)
        else:
            c=type.__new__(meta,classname,bases,classDict)
        Compound.mdsdtypeToClass[classDict['dtype_mds']]=c
        return c

class _Action(Compound):
    """
    An Action is used for describing an operation to be performed
    by an MDSplus action server. Actions are typically dispatched
    using the mdstcl DISPATCH command
    """
    dtype_mds=202
    fields=('dispatch','task','errorLog','completionMessage','performance')
Action=_compoundMeta('Action',(_Action,),{})
    
class _Call(Compound):
    """
    A Call is used to call routines in shared libraries.
    """
    dtype_mds=212
    fields=('image','routine')
    _opcode_name='retType'
Call=_compoundMeta('Call',(_Call,),{})
    
class _Conglom(Compound):
    """
    A Conglom is used at the head of an MDSplus conglomerate.
    A conglomerate is a set of tree nodes used to define a
    device such as a piece of data acquisition hardware. A
    conglomerate is associated with some external code 
    providing various methods which can be performed on the
    device. The Conglom class contains information used for
    locating the external code.
    """
    dtype_mds=200
    fields=('image','model','name','qualifiers')
Conglom=_compoundMeta('Conglom',(_Conglom,),{})
    
class _Dependency(Compound):
    """A Dependency object is used to describe action dependencies. This is a legacy class and may not be recognized by
    some dispatching systems
    """
    dtype_mds=208
    fields=('arg1','arg2')
Dependency=_compoundMeta('Dependency',(_Dependency,),{})

class _Dimension(Compound):
    """
    A dimension object is used to describe a signal dimension,
    typically a time axis. It provides a compact description
    of the timing information of measurements recorded by devices
    such as transient recorders. It associates a Window object
    with an axis. The axis is generally a range with possibly
    no start or end but simply a delta. The Window object is
    then used to bracket the axis to resolve the appropriate
    timestamps.
    """
    dtype_mds=196
    fields=('window','axis')
Dimension=_compoundMeta('Dimension',(_Dimension,),{})

class _Dispatch(Compound):
    """
    A Dispatch object is used to describe when an where an
    action should be dispatched to an MDSplus action server.
    """
    dtype_mds=203
    fields=('ident','phase','when','completion')

    def __init__(self,*args,**kwargs):
      if 'opcode' not in kwargs:
        if 'dispatch_type' not in kwargs:
            kwargs['dispatch_type']=2
        kwargs['opcode']=kwargs['dispatch_type']
        Compound.__init__(self,args=args,params=kwargs)
        if self.completion is None:
           self.completion = None
Dispatch=_compoundMeta('Dispatch',(_Dispatch,),{})

class _Method(Compound):
    """
    A Method object is used to describe an operation to
    be performed on an MDSplus conglomerate/device
    """
    dtype_mds=207
    fields=('timeout','method','object')
Method=_compoundMeta('Method',(_Method,),{})

class _Procedure(Compound):
    """
    A Procedure is a deprecated object
   """
    dtype_mds=206
    fields=('timeout','language','procedure')
Procedure=_compoundMeta('Procedure',(_Procedure,),{})
    
class _Program(Compound):
    """A Program is a deprecated object"""
    dtype_mds=204
    fields=('timeout','program')
Program=_compoundMeta('Program',(_Program,),{})
    
class _Range(Compound):
    """
    A Range describes a ramp. When used as an axis in
    a Dimension object along with a Window object it can be
    used to describe a clock. In this context it is possible
    to have missing begin and ending values or even have the
    begin, ending, and delta fields specified as arrays to
    indicate a multi-speed clock.
    """
    dtype_mds=201
    fields=('begin','ending','delta')

    def decompile(self):
        parts=list()
        for arg in self.args:
            parts.append(str(makeData(arg).decompile()))
        return ' : '.join(parts)
Range=_compoundMeta('Range',(_Range,),{})
        
class _Param(Compound):
  """Param is a compound object containing a value field, a help field and a validation field"""
  dtype_mds=194
  fields=('value','help','validation')
Param=_compoundMeta('Param',(_Param,),{})

class _Slope(Compound):
    """
    Slope is a deprecated object. Similar to Range but order
    of args is 'delta','begin','ending'. It will internally
    be converted to a Range before evaluation.
    """
    dtype_mds=198
    fields=('delta', 'begin','ending')
Slope=_compoundMeta('Slope',(_Slope,),{})

class _Routine(Compound):
    """
    A Routine is a deprecated object"""
    dtype_mds=205
    fields=('timeout','image','routine')
Routine=_compoundMeta('Routine',(_Routine,),{})
    
class _Signal(Compound):
    """
    A Signal is used to describe a measurement, usually time
    dependent, and associated the data with its independent
    axis (Dimensions). When Signals are indexed using s[idx],
    the index is resolved using the dimension of the signal
    """
    dtype_mds=195
    fields=('value','raw')
    
    def _getDims(self):
        return self.getArguments()

    dims=property(_getDims)
    """The dimensions of the signal"""
        
#    def decompile(self):
#        arglist=list()
#        for arg in self.args:
#            arglist.append(makeData(arg).decompile())
#        return 'Build_Signal('+','.join(arglist)+')'

    def dim_of(self,idx=0):
        """Return the signals dimension
        @rtype: Data
        """
        if idx < len(self.dims):
            return self.dims[idx]
        else:
            return makeData(None)

    def __getitem__(self,idx):
        """Subscripting <==> signal[subscript]. Uses the dimension information for subscripting
        @param idx: index or Range used for subscripting the signal based on the signals dimensions
        @type idx: Data
        @rtype: Signal
        """
        return _tdi.SUBSCRIPT(self,makeData(idx)).evaluate()
    
    def getDimensionAt(self,idx=0):
        """Return the dimension of the signal
        @param idx: The index of the desired dimension. Indexes start at 0. 0=default
        @type idx: int
        @rtype: Data
        """
        try:
            return self.dims[idx]
        except:
            return None

    def getDimensions(self):
        """Return all the dimensions of the signal
        @rtype: tuple
        """
        return self.dims

    def setDimensionAt(self,idx,value):
        """Set the dimension
        @param idx: The index into the dimensions of the signal.
        @rtype: None
        """
        return self.setArgumentAt(idx,value)

    def setDimensions(self,value):
        """Set all the dimensions of a signal
        @param value: The dimensions
        @type value: tuple
        @rtype: None
        """
        return self.setArguments(value)
Signal=_compoundMeta('Signal',(_Signal,),{})

class _Window(Compound):
    """
    A Window object can be used to construct a Dimension
    object. It brackets the axis information stored in the
    Dimension to construct the independent axis of a signal.
    """
    dtype_mds=197
    fields=('startIdx','endIdx','timeAt0')

#    def decompile(self):
#        return 'Build_Window('+makeData(self.startIdx).decompile()+','+makeData(self.endIdx).decompile()+','+makeData(self.timeAt0)+')'
Window=_compoundMeta('Window',(_Window,),{})

class _Opaque(Compound):
    """
    An Opaque object containing a binary uint8 array and a string identifying the type.
    """
    dtype_mds=217
    fields=('data','otype')
   
    def getImage(self):
        try:
            import Image
        except:
            print("Image module required but unable to import it")
            return None
        try:
            import StringIO
        except:
            print("StringIO module required but unable to import it")
            return None
        return Image.open(StringIO.StringIO(makeData(self.getData()).data().data))

    def fromFile(filename,typestring):
      """Read a file and return an Opaque object
         @param filename: Name of file to read in
         @type filename: str
         @param typestring: String to denote the type of file being stored
         @type typestring: str
         @rtype: Opaque instance
      """
      f = open(filename,'rb')
      try:
        opq=Opaque(makeData(_NP.fromstring(f.read(),dtype="uint8")),typestring)
      finally:
        f.close()
      return opq
    fromFile=staticmethod(fromFile)
Opaque=_compoundMeta('Opaque',(_Opaque,),{})

class Apd(Data):
    """The Apd class represents the Array of Pointers to Descriptors structure.
    This structure provides a mechanism for storing an array of non-primitive items.
    """

    mdsclass=196
    mdsdtypeToClass=dict()


    def __hasBadTreeReferences__(self,tree):
        for desc in self.descs:
            if isinstance(desc,Data) and desc.__hasBadTreeReferences__(tree):
                return True
        return False
    
    def __fixTreeReferences__(self,tree):
        ans=_copy.deepcopy(self)
        descs=list(ans.descs)
        for idx in range(len(descs)):
            if isinstance(descs[idx],Data) and descs[idx].__hasBadTreeReferences__(tree):
                descs[idx]=descs[idx].__fixTreeReferences__(tree)
        ans.descs=tuple(descs)
        return ans
    
    def __init__(self,descs,dtype=0):
        """Initializes a Apd instance
        """
        if isinstance(descs,tuple):
            self.descs=descs
            self.dtype_mds=dtype
        else:
            raise TypeError("must provide tuple of items when creating ApdData")
        return

    def __len__(self):
        """Return the number of descriptors in the apd"""
        return len(self.descs)
    
    def __getitem__(self,idx):
        """Return descriptor(s) x.__getitem__(idx) <==> x[idx]
        @rtype: Data|tuple
        """
        try:
            return self.descs[idx]
        except:
            return None
        return

    def __setitem__(self,idx,value):
        """Set descriptor. x.__setitem__(idx,value) <==> x[idx]=value
        @rtype: None
        """
        l=list(self.descs)
        while len(l) <= idx:
            l.append(None)
        l[idx]=value
        self.descs=tuple(l)
        return None
   
    def getDescs(self):
        """Returns the descs of the Apd.
        @rtype: tuple
        """
        return self.descs

    def getDescAt(self,idx=0):
        """Return the descriptor indexed by idx. (indexes start at 0).
        @rtype: Data
        """
        return self[idx]

    def setDescs(self,descs):
        """Set the descriptors of the Apd.
        @type descs: tuple
        @rtype: None
        """
        if isinstance(descs,tuple):
            self.descs=descs
        else:
            raise TypeError("must provide tuple")
        return

    def setDescAt(self,idx,value):
        """Set a descriptor in the Apd
        """
        self[idx]=value
        return None

    def append(self,value):
        """Append a value to apd"""
        self[len(self)]=value

    def data(self):
        """Returns native representation of the apd"""
        l=list()
        for d in self.descs:
            l.append(d.data())
        return tuple(l)

    def _dataFromDescriptor(descr):
      d=_C.cast(_C.pointer(descr),_C.POINTER(_Descriptor_a)).contents
      num=d.arsize/d.length
      descptrs=_C.cast(d.pointer,_C.POINTER(_C.POINTER(_Descriptor)*num)).contents
      ans=Apd((),)
      for i in range(num):
        if descptrs[i]:
          arg=descptrs[i].contents.value
        else:
          arg=None
        ans.append(arg)
      if d.dtype in Apd.mdsdtypeToClass:
        ans=Apd.mdsdtypeToClass[d.dtype](ans)
      return ans
    _dataFromDescriptor=staticmethod(_dataFromDescriptor)

    def _getDescriptor(self):
      """Return a MDSplus descriptor"""
      d=_Descriptor_a()
      d.length=_C.sizeof(_C.c_void_p(0))
      d.dtype=self.dtype_mds
      d.dclass=self.mdsclass
      d.scale=0
      d.digits=0
      d.aflags=0
      d.dimct=1
      descs=self.descs
      ddescs=list()
      num=len(descs)
      d.arsize=num*_C.sizeof(_C.c_void_p(0))
      ptrs=(_C.c_void_p*num)()
      for i in range(num):
        if descs[i] is None:
          ptrs[i]=_C.c_void_p(0)
        else:
          desc=descs[i].descriptor
          ddescs.append(desc)
          ptrs[i]=_C.cast(_C.pointer(desc),_C.c_void_p)
      d.pointer=d.a0=_C.cast(_C.pointer(ptrs),_C.c_void_p)
      d.original=(self,descs,ddescs)
      return _descrWithUnitsAndError(self,d)
    descriptor=property(_getDescriptor)
Data.mdsclassToClass[Apd.mdsclass]=Apd

class Dictionary(dict,Apd):
    """dictionary class"""

    dtype_mds=216

    def __hasBadTreeReferences__(self,tree):
        for v in self.itervalues():
            if isinstance(v,Data) and v.__hasBadTreeReferences__(tree):
                return True
        return False

    def __fixTreeReferences__(self,tree):
        ans = _copy.deepcopy(self)
        for key,value in ans.iteritems():
            if isinstance(value,Data) and value.__hasBadTreeReferences__(tree):
                ans[key]=value.__fixTreeReferences__(tree)
        return ans
    
    def __init__(self,value=None):
        if value is not None:
            if isinstance(value,Apd):
                for idx in range(0,len(value),2):
                    key=value[idx]
                    if isinstance(key,Scalar):
                        key=key.value
                    if isinstance(key,_NP.string_):
                        key=str(key)
                    elif isinstance(key,_NP.int32):
                        key=int(key)
                    elif isinstance(key,_NP.float32) or isinstance(key,_NP.float64):
                        key=float(key)
                    val=value[idx+1]
                    if isinstance(val,Apd):
                        val=Dictionary(val)
                    self.setdefault(key,val)
            elif isinstance(value,dict):
                for key,val in value.items():
                    self.setdefault(key,val)
            else:
                raise TypeError('Cannot create Dictionary from type: '+str(type(value)))

    def __getattr__(self,name):
      if name == 'descs':
        ans=list()
        for k,v in self.iteritems():
          ans.append(makeData(k))
          ans.append(makeData(v))
        return ans
      elif name in self.keys():
        return self[name]
      else:
        raise AttributeError("type 'Dictionary' has no attribute '%s" % name)

    def __setattr__(self,name,value):
        if name in self.keys():
            self[name]=value
        elif hasattr(self,name):
            self.__dict__[name]=value
        else:
            self.setdefault(name,value)

    def data(self):
        """Return native representation of data item"""
        d=dict()
        for key,val in self.items():
            d.setdefault(key,val.data())
        return d
        
    def __str__(self):
        return dict.__str__(self)
Apd.mdsdtypeToClass[Dictionary.dtype_mds]=Dictionary
 
class List(list,Apd):
    """list class"""

    dtype_mds=214

    def __hasBadTreeReferences__(self,tree):
        for v in self:
            if isinstance(v,Data) and v.__hasBadTreeReferences__(tree):
                return True
        return False

    def __fixTreeReferences__(self,tree):
        ans = _copy.deepcopy(self)
        for idx in range(len(ans)):
            if isinstance(ans[idx],Data) and ans[idx].__hasBadTreeReferences__(tree):
                ans[idx]=ans[idx].__fixTreeReferences__(tree)
        return ans
    
    def __init__(self,value=None):
        if value is not None:
            if isinstance(value,Apd) or isinstance(value,list) or isinstance(value,tuple):
                for idx in range(len(value)):
                    super(List,self).append(value[idx])
            else:
                raise TypeError('Cannot create List from type: '+str(type(value)))

    def __getattr__(self,name):
      if name == 'descs':
        ans=list()
        for v in self:
          ans.append(makeData(v))
        return ans
      else:
        raise AttributeError("type 'List' has no attribute '%s" % name)

    def __str__(self):
        return list.__str__(self)
Apd.mdsdtypeToClass[List.dtype_mds]=List

class TdiException(Exception):
  pass

class MdsException(Exception):
  pass

_tdi=_mimport('tdibuiltins',1)
_tree=_mimport('tree',1)
