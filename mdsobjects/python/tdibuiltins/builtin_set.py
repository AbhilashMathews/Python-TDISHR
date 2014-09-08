import os as _os
import ctypes as _C
import numpy as _NP

if '__package__' not in globals() or __package__ is None or len(__package__)==0:
  def _mimport(name,level):
    try:
      return __import__(name,globals())
    except:
      _current_d=_os.getcwd()
      try:
        _os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
        for i in range(1,level):
          _os.chdir(_os.pardir)
        ans = __import__(name,globals())
      finally:
        _os.chdir(_current_d)
      return ans
else:
  def _mimport(name,level):
    try:
      return __import__(name,globals(),{},[],level)
    except ValueError:
      return __import__(name,globals())

_tree=_mimport('tree',2)
_data=_mimport('data',2)

class Builtin(_data.Compound):
    """Function builtin and superclass to all other builtins"""
    dtype_mds=199
    min_args = None
    max_args = None
    precedence=0
    syntax=None
    description=None
    CCodeName = None
    builtins_by_name=dict()
    builtins_by_opcode=dict()
    def __new__(klass, *args, **kwargs):
        if klass == Builtin:
            if isinstance(args[0],str) and args[0].upper() in klass.builtins_by_name:
                ans = klass.builtins_by_name[args[0].upper()](args=args[1])
                ans.from_builtin=True
                return ans
            elif args[0] in klass.builtins_by_opcode:
                ans = klass.builtins_by_opcode[args[0]](args=args[1])
                ans.from_builtin=True
                return ans
            raise _data.TdiException("Not a builtin, %s" % (str(args[0]),))
        return super(Builtin,klass).__new__(klass)

    def __init__(self,*args,**kwargs):
        """Create a compiled MDSplus function reference.
        Number of arguments allowed depends on the opcode supplied.
        """
        if hasattr(self,'opc'):
            return
        if hasattr(self,'from_builtin'):
            args=args[1]
        elif 'args' in kwargs:
            args=kwargs['args']
        if self.min_args is not None and len(args) < self.min_args:
            raise _data.TdiException("Builtin: %s requires at least %d arguments, %d provided" % (self.name,self.min_args,len(args)))
        if self.max_args is not None and len(args) > self.max_args:
            raise _data.TdiException("Builtin: %s requires no more than %d arguments, %d provided" % (self.name,self.max_args,len(args)))
        args=list(args)
        for i in range(len(args)):
          args[i]=_data.makeData(args[i])
        self.args=tuple(args)

    def loadBuiltins(klass,globals_list):
        for item in globals_list.values():
            try:
                if issubclass(item,Builtin):
                    if item.name in klass.builtins_by_name:
                        raise _data.TdiException('duplicate builtin found: %s' % (item.name,))
                    else:
                        klass.builtins_by_name[item.name]=item
                    if item.opcode in klass.builtins_by_opcode:
                        raise _data.TdiException('duplicate builtin opcode found: %d' % (item.opcode))
                    else:
                        klass.builtins_by_opcode[item.opcode]=item
            except:
                pass
    loadBuiltins=classmethod(loadBuiltins)


    def evaluate(self):
        if hasattr(self,'_evaluate') and self.usePython:
          return self._evaluate()
        else:
          return _data.TdiEvaluate(self)

    def evaluateArgs(self):
        def evaluateArg(arg):
            while isinstance(arg,(Builtin,_tree.TreeNode)):
              arg=arg.evaluate()
              if isinstance(arg,AS_IS):
                break
            return self.makeData(arg)

        ans=list()
        for arg in self.args:
          try:
            arg=evaluateArg(arg)
          except:
            pass
          ans.append(arg)
        return ans

    def getDoc(c):
        if issubclass(c,NotSupported):
            return None
        native = hasattr(c,'_evaluate')
        if c.max_args is None:
            max_args="255"
        else:
            max_args=str(c.max_args)
        if c.min_args is None:
            min_args="0"
        else:
            min_args=str(c.min_args)
        if c.syntax is None:
            if c.max_args == 0:
                if c.name.startswith('$'):
                    syntax=c.name
                else:
                    syntax=c.name+'()'
            elif c.max_args < 6:
                syntax=c.name+'('
                for i in range(c.max_args-1):
                    syntax=syntax+'arg%d,'%i
                syntax=syntax+'arg%d' % (c.max_args-1,)+')'
            else:
                syntax=c.name+"(arg0,arg1,argn,...)"
        else:
            syntax=c.syntax
        if c.__doc__ is None:
            description="No information provided"
        else:
            description=c.__doc__
        if c.name.startswith('$'):
          name='d%s (tdi $%s)' % (c.name[1:],c.name[1:])
        else:
          name=c.name
        if len(c.getCCodeName())==0:
          codename="None"
        else:
          codename="Tdi"+c.getCCodeName()
        d=description.split('\n')
        description='        '+'\n        '.join(d)
        return """%s
    Builtin Name:    %s
    TdiShr Function: %s
    Opcode number:   %s
    Min Arguments:   %s
    Max arguments:   %s
    Compiler syntax: %s
    Native python:   %s
    Description:\n%s\n\n""" % (name,name,codename,c.opcode,min_args,max_args,syntax,str(native),description)
    getDoc=classmethod(getDoc)

    def _descriptorPointer(self):
      return self.evaluate().descrPtr
    descriptorPointer=property(_descriptorPointer)

    def getCCodeName(klass):
        if klass.CCodeName is None:
            parts=klass.name.split('_')
            for idx in range(len(parts)):
                if parts[idx].startswith('$'):
                    parts[idx]=parts[idx][1:].capitalize()
                else:
                    parts[idx]=parts[idx].capitalize()
            name=''.join(parts)
        else:
            name=klass.CCodeName
        return name
    getCCodeName=classmethod(getCCodeName)

    def getCCodeGlue(klass):
        if issubclass(klass,NotSupported):
            return """int Tdi%s(struct descriptor *arg0,...) {return TdiNO_OPC;}""" % (klass.getCCodeName(),)
        else:
            return """int Tdi%s(struct descriptor *arg0,...) {
  va_list ap;
  struct descriptor *args[256];
  int nArgs;
  va_start(ap,arg0);
  args[0]=arg0;
  for (nArgs=1; (args[nArgs]=va_arg(ap,struct descriptor *)) != MdsEND_ARG; nArgs++);
  return EvaluateBuiltin(%d,"%s",nArgs,args);
}""" % (klass.getCCodeName(),klass.opcode,klass.__name__)
    getCCodeGlue=classmethod(getCCodeGlue)

_data.Compound.mdsdtypeToClass[Builtin.dtype_mds]=Builtin

_toBeCompleted=Builtin
_completed=Builtin

class NotSupported(_completed):
    pass

def _int32ToFloat(arg):
    if (isinstance(arg,_NP.ndarray) and isinstance(arg[0],_NP.int32)) or isinstance(arg,_NP.int32):
        ans=_NP.float32(arg)
    else:
        ans=arg
    return ans

def _dataArg(arg):
    try:
        arg=arg.data()
    except:
        arg=Builtin.makeData(arg).data()
    return arg

def _dataArgs(args):
    ans=list()
    for arg in args:
        ans.append(_dataArg(arg))
    return ans

def _updateSignal(signal,value):
    args=[signal.makeData(value),None]
    for d in signal.dims:
	args.append(d)
    return _data.Signal(tuple(args))
    signal.value=signal.makeData(value)
    signal.raw=None
    return signal

class _constant(_completed):
    def __str__(self):
        return self.name
    def _evaluate(self):
        return self.cvalue

class dPLACEHOLDER(_completed):
    """Argument placeholder. Object not actually created in
    compilations. Placeholders are replaced by arguments passed
    to the compile operation. A placeholder can be simply $
    or they can be trailed by a number, i.e. $2 specifying
    the second argument (arguments are indexed beginning with 1
    for the first argument using positional placeholders).
    if a $n is used as a placeholder, subsequent $ placeholders
    without a position number will use the next placeholder after
    $n. For example:

      compile("_x=$//$3//$1//$",'how ','are ','you ')

    would produce the string:

      "how you how are" """
    min_args=0
    max_args=0
    name='$'
    CCodeName="dollar"
    opcode=0

class d2PI(_constant):
    """CONSTANT: 2PI - equivalent to circumference of a circle divided by its radius (approx 6.2831853072)"""
    min_args=0
    max_args=0
    name='$2PI'
    CCodeName='2Pi'
    opcode=372
    cvalue=_data.Float32(_NP.pi*2)

class dA0(_constant):
    """CONSTANT: "$A0" BOHR Radius == 5.29177249e-11 m"""
    max_args=0
    name='$A0'
    opcode=1
    cvalue=_data.Float32(52.917726E-12).setUnits('m').setError(_data.Float32(2400E-21))

class dALPHA(_constant):
    """CONSTANT: "$ALPHA" Fine-structure == 7.29735308e-3"""
    max_args=0
    name='$ALPHA'
    opcode=2
    cvalue=_data.Float32(7.29735308e-3).setError(_data.Float32(0.00000033e-3))

class dAMU(_constant):
    """CONSTANT: "$AMU" Unified atomic mass unit == 1.6605402e-27"""
    max_args=0
    name='$AMU'
    opcode=3
    cvalue=_data.Float32(1.6605402e-27).setError(_data.Float32(0.0000010e-27)).setUnits("kg")

class dATM(_constant):
    """CONSTANT: "$ATM" Atmospheric pressure == 101325. Pa"""
    max_args=0
    name='$ATM'
    opcode=405
    cvalue=_data.Float32(101325.).setUnits("Pa")

class dC(_constant):
    """CONSTANT: "$C" Speed of light == 299792458. m/s"""
    max_args=0
    name='$C'
    opcode=4
    cvalue=_data.Float32(299792458.).setUnits('m/s')

class dCAL(_constant):
    """CONSTANT: "$CAL" Calorie == 4.1868 J"""
    max_args=0
    name='$CAL'
    opcode=5
    cvalue=_data.Float32(4.1868).setUnits('J')

class dDEFAULT(_completed):
    """SPECIAL: "$DEFAULT" Current default tree node (TreeNode) location"""
    min_args=0
    max_args=0
    name='$DEFAULT'
    CCodeName='MdsDefault'
    opcode=386
    def _evaluate(self):
        return _tree.Tree().default.path

class dDEGREE(_constant):
    """CONSTANT: "$DEGREE" pi/180 == .01745329252"""
    max_args=0
    name='$DEGREE'
    opcode=6
    cvalue=_data.Float32(_NP.pi/180)

class dEPSILON0(_constant):
    """CONSTANT: "$EPSILON0" Permitivity of vacuum == 8854.19E-15 F/m"""
    min_args=0
    max_args=0
    name='$EPSILON0'
    opcode=406
    cvalue=_data.Float32(8.8541882159454133e-12).setUnits("F/m")

class dEV(_constant):
    """CONSTANT: "$EV" Electron volt == 1.60217733e-19	 J/eV"""
    max_args=0
    name='$EV'
    opcode=7
    cvalue=_data.Float32(1.60217733e-19).setUnits('J/eV').setError(_data.Float32(0.00000049e-19))

class dEXPT(_completed):
    """SPECIAL: "$EXPT" Current tree name"""
    min_args=0
    max_args=0
    name='$EXPT'
    opcode=387
    def _evaluate(self):
        return self.makeData(_tree.Tree().tree)

class dFALSE(_constant):
    """CONSTANT: "$FALSE" False == 0BU"""
    max_args=0
    name='$FALSE'
    opcode=8
    cvalue=_data.Uint8(0);

class dFARADAY(_constant):
    """CONSTANT: "$FARADAY" Faraday constant == 9.6485309e4 C/mol"""
    max_args=0
    name='$FARADAY'
    opcode=9
    cvalue= _data.Float32(9.6485309e4).setUnits('C/mol').setError(_data.Float32(0.0000029e4))

class dG(_constant):
    """CONSTANT: "$G" Gravitational constant == 6.67259e-11 m^3/s^2/kg"""
    max_args=0
    name='$G'
    opcode=10
    cvalue=_data.Float32(6.67259e-11).setUnits('m^3/s^2/kg').setError(_data.Float32(0.00085))

class dGAS(_constant):
    """CONSTANT: "$GAS" Gas constant == 8.314510 J/K/mol"""
    max_args=0
    name='$GAS'
    opcode=11
    cvalue=_data.Float32(8.314510).setUnits('J/K/mol').setError(_data.Float32(0.000070))

class dGN(_constant):
    """CONSTANT: "$GN" acceleration of gravity == 9.80665 m/s^2"""
    min_args=0
    max_args=0
    name='$GN'
    opcode=407
    cvalue=_data.Float32(9.80665).setUnits("m/s^2")

class dH(_constant):
    """CONSTANT: "$H" Planck constant == 6.6260755e-34 J*s"""
    max_args=0
    name='$H'
    opcode=12
    cvalue=_data.Float32(6.6260755e-34).setUnits('J*s').setError(_data.Float32(0.0000040))

class dHBAR(_constant):
    """CONSTANT: "$HBAR" Planck constant/2PI == 1.05457266e-34 J*s"""
    max_args=0
    name='$HBAR'
    opcode=13
    cvalue=_data.Float32(1.05457266e-34).setUnits('J*s').setError(_data.Float32(0.00000063))

class dI(_constant):
    """CONSTANT: "$I" Imaginary == cmplx(0,1)"""
    max_args=0
    name='$I'
    opcode=14
    cvalue=_data.Complex64(1j)

class dK(_constant):
    """CONSTANT: "$K" Boltzmann constant == 1.380658e-23 J/K"""
    max_args=0
    name='$K'
    opcode=15
    cvalue=_data.Float32(1.380658e-23).setUnits('J/K').setError(_data.Float32(0.000012e-23))

class dME(_constant):
    """CONSTANT: "$ME" Mass of electron == 9.1093897e-31 kg"""
    max_args=0
    name='$ME'
    opcode=16
    cvalue=_data.Float32(9.1093897e-31).setUnits('kg').setError(_data.Float32(0.0000054e-31))

class dMISSING(_constant):
    """SPECIAL: "$MISSING" Missing value"""
    max_args=0
    name='$MISSING'
    opcode=17
    def _evaluate(self):
        return self

class dMP(_constant):
    """CONSTANT: "$MP" Mass of proton == 1.6726231e-27 kg"""
    max_args=0
    name='$MP'
    opcode=18
    cvalue=_data.Float32(1.6726231e-27).setUnits('kg').setError(_data.Float32(0.0000010e-27))

class dMU0(_constant):
    """CONSTANT: "$MU0" Permeability of vacuum == 12.566370614e-7 N/A^2"""
    min_args=0
    max_args=0
    name='$MU0'
    opcode=408
    cvalue=_data.Float32(12.566370614e-7).setUnits("N/A^2")

class dN0(_constant):
    """CONSTANT: "$N0" Loschmidt's number ==2.686763e25 /m^3""" 
    max_args=0
    name='$N0'
    opcode=19
    cvalue= _data.Float32(2.686763e25).setUnits('/m^3').setError(_data.Float32(0.000023e25))

class dNA(_constant):
    """CONSTANT: "$NA" Avogadro number == 6.0221367e23 /mol"""
    max_args=0
    name='$NA'
    opcode=20
    cvalue= _data.Float32(6.0221367e23).setUnits('/mol').setError(_data.Float32(0.0000036e23))

class dNARG(_toBeCompleted):
    """SPECIAL: "$NARG" Actual arguments used to invoke the FUN"""
    min_args=0
    max_args=0
    name='$NARG'
    opcode=373

class dP0(_constant):
    """CONSTANT: "$P0" Atmospheric pressure == 1.01325E5 Pa"""
    max_args=0
    name='$P0'
    opcode=21
    cvalue= _data.Float32(1.01325e5).setUnits('Pa')

class dPI(_constant):
    """CONSTANT: "$PI" Circumference/radius == 3.1415926536"""
    max_args=0
    name='$PI'
    opcode=22
    cvalue=_data.Float32(_NP.pi)

class dQE(_constant):
    """CONSTANT: "$QE" Charge on electron == 1.60217733e-19 C"""
    max_args=0
    name='$QE'
    opcode=23
    cvalue=_data.Float32(1.60217733e-19).setUnits('C').setError(_data.Float32(0.000000493-19))

class dRE(_constant):
    """CONSTANT: "$RE" Classical electron rad == 2.81794092e-15	m"""
    max_args=0
    name='$RE'
    opcode=24
    cvalue=_data.Float32(2.81794092e-15).setUnits('m').setError(_data.Float32(0.00000038e-15))

class dROPRAND(_constant):
    """SPECIAL: "$ROPRAND" Reserved operand "float nan" """
    max_args=0
    name='$ROPRAND'
    opcode=25
    cvalue=_data.Float32(_NP.nan)

class dRYDBERG(_constant):
    """CONSTANT: "$RYDBERG" Rydberg constant == 1.0973731534e7 /m"""
    max_args=0
    name='$RYDBERG'
    opcode=26
    cvalue=_data.Float32(1.0973731534e7).setUnits('/m').setError(_data.Float32(0.0000000013e7))

class dSHOT(_completed):
    """SPECIAL: "$SHOT" Current tree's shot number"""
    min_args=0
    max_args=0
    name='$SHOT'
    opcode=388
    def _evaluate(self):
        return self.makeData(_tree.Tree().shot)

class dSHOTNAME(_completed):
    """SPECIAL: "$SHOTNAME" Currten tree's shot number as text, can return MODEL"""
    min_args=0
    max_args=0
    name='$SHOTNAME'
    opcode=444
    def _evaluate(self):
        s=_tree.Tree().shot
        if s == -1:
            ans="MODEL"
        else:
            ans=str(s)
        return self.makeData(ans)

class dT0(_constant):
    """CONSTANT: "$T0" Standard temperature 273.16 K"""
    max_args=0
    name='$T0'
    opcode=27
    cvalue=_data.Float32(273.16).setUnits('K')

class dTHIS(_toBeCompleted):
    """SPECIAL: "$THIS" Signal or param associated with one of its parts"""
    min_args=0
    max_args=0
    name='$THIS'
    opcode=403

class dTORR(_constant):
    """CONSTANT: "$TORR" 1mm Hg pressure == 1.3332e2 Pa"""
    max_args=0
    name='$TORR'
    opcode=28
    cvalue=_data.Float32(1.3332e2).setUnits('Pa')

class dTRUE(_constant):
    """CONSTANT: "$TRUE" True == 1bu"""
    max_args=0
    name='$TRUE'
    opcode=29
    cvalue=_data.Uint8(1)

class dVALUE(_completed):
    """SPECIAL: "$VALUE" Raw field in a signal or value field in a param or subscript dimensional element"""
    min_args=0
    max_args=0
    name='$VALUE'
    opcode=30
    stack=list()
    def _evaluate(self):
      if len(self.stack)==0:
        return None
      else:
        return self.stack[-1]
    def _push(kls,value):
      kls.stack.append(value)
    _push=classmethod(_push)
    def _pop(kls):
      kls.stack.__delitem__(len(kls.stack)-1)
    _pop=classmethod(_pop)

class _PART_OF(_completed):
  """Superclass of xxxx_OF builtins. Returns the xxxx attribute of object or raises an error"""
  def _evaluate(self):
    args=self.evaluateArgs()
    arg=args[0]
    if hasattr(self,'partnames'):
      partnames=self.partnames
    else:
      partnames=(self.name[0:-3].lower(),)
    if not isinstance(arg,Builtin):
      for partname in partnames:
        if hasattr(arg,partname):
          try:
            return arg.__getattr__(partname)
          except:
            return arg.__getattribute__(partname)
    if isinstance(arg,(_data.Compound,_data.Apd)):
      for a in arg.args:
        try:
          return type(self)(a)._evaluate()
        except:
          pass
    raise _data.TdiException("Object of type %s has no %s attribute" % (str(type(args[0])),self.name[0:-3].lower()))

class ABORT(_completed):
    """      Miscellaneous. 
      
      Abort an expresion by causing an error.

      
      Arguments Any, ignored.


      Result..  None, error status.


      Example.  IF_ERROR(A,B,ABORT()) aborts if both members are bad."""
    min_args=0
    max_args=255
    name='ABORT'
    opcode=31
    def _evaluate(self):
        raise _data.TdiException("%TDI-E-TdiABORT, Program requested abort")
# test compatibility may want to add this enhancement
#        try:
#            args=str(self.args)
#        except:
#            args=""
#        raise _data.TdiException("ABORT! %s" % (args,))

class ABS(_completed):
    """      F90 Numeric Elemental. 
      
      Absolute value.

      
      Argument. A must be numeric.


      Signals.  Same as A.
      Units...  Same as A.
      Form....  Same as A except if A is complex, the result is real.


      Result..  Unsigned integers are unchanged, negative integers
                and reals are negated, complex numbers get square roots
                of the sum of the squares of real and imaginary parts.
                The complex number parts are scaled to avoid overflow.


      Example.  ABS(CMPLX(3.0,4.0)) is 5.0.


      See also. ABS1 and ABSSQ for complex number to avoid a square root.
                ARG for the complex angle."""
    min_args=1
    max_args=1
    name="ABS"
    opcode=32
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            if hasattr(args[0],'_units'):
                ans = self.makeData(abs(args[0]._value)).setUnits(args[0]._units)
            else:
                ans = self.makeData(abs(args[0]._value))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ABS(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ABS function: %s" % (str(type(args[0])),))
        return ans

class ABS1(_completed):
    """      Numeric Elemental. 
      
      Absolute value with L1 norm.

      Argument. A must be numeric.

      Signals.  Same as A.
      Units...  Same as A.
      Form....  Same as A except if A is complex, the result is real.

      Result..  Unsigned integers are unchanged, negative integers
                and reals are negated, complex numbers become the sums
                of the absolute values of the real and imaginary parts.

      Example.  ABS1(CMPLX(3.0,-4.0)) is 7.0."""
    min_args=1
    max_args=1
    name="ABS1"
    opcode=33
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans=self.makeData(abs(args[0].real)+abs(args[0].imag))
            if hasattr(args[0],'_units'):
                ans=ans.setUnits(args[0].units)
        elif isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[0],ABS1(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ABS1 function: %s" % (str(type(args[0])),))
        return ans

class ABSSQ(_completed):
    """      Numeric Elemental. 
      
      Absolute value squared.

      Argument. A must be numeric.

      Signals.  Same as A.
      Units...  Same as for A * A.
      Form....  Same as A except if A is complex, the result is real.

      Result..  Integers may lose significance. Integers and reals are
                squared, complex numbers become the sums of the squares
                of the real and imaginary parts.

      Example.  ABSSQ(CMPLX(3.0,4.0)) is 25.0."""
    min_args=1
    max_args=1
    name="ABSSQ"
    CCodeName="AbsSq"
    opcode=34
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans=self.makeData(abs(args[0].real)**2.+abs(args[0].imag)**2.)
            if isinstance(args[0],_data.Complex64):
                ans=_data.Float32(ans)
            elif isinstance(args[0],_data.Complex128):
                ans=_data.Float64(ans)
            elif isinstance(args[0],_data.Complex64Array):
                ans=_data.Float32Array(ans)
            elif isinstance(args[0],_data.Complex128Array):
                ans=_data.Float64Array(ans)
            else:
                ans=type(args[0])(ans)
            if hasattr(args[0],'_units'):
                ans=ans.setUnits(args[0].units+"*"+args[0].units)
        elif isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[0],ABSSQ(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ABSSQ function: %s" % (str(type(args[0])),))
        return ans

class ACCUMULATE(_completed):
    """      Transformation. 
      
      Running sum of all the elements of ARRAY along dimension
                DIM corresponding to the true elements of MASK.

      Arguments Optional: DIM, MASK.
        ARRAY   numeric array.
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY.
        MASK    logical and conformable to ARRAY.

      Signals.  Same as ARRAY.
      Units...  Same as ARRAY.
      Form....  Same type and shape as ARRAY.
      Result..  The result is the running sum of the elements of
                ARRAY, using only those with true MASK values and value
                not equal to the reserved operand ($ROPRAND). With DIM,
                the value of an element of the result is the running sum of
                the ARRAY elements with dimension DIM fixed as the element
                number of the result. Without DIM, the result is the sum
                from the first element ignoring the shape.
                If no value is found, 0 is given.

      Examples. ACCUMULATE([1,2,3]) is [1,3,6].
                ACCUMULATE(_C,,_C GT 0) finds the running sum of all
                positive element of C.
                If _B=[[1, 3, 5],[2, 4, 6]]
                ACCUMULATE(_B) is [[1, 4, 9],[11, 15, 21]]
                ACCUMULATE(_B,0) is [[1, 4, 9],[2, 6, 12]]
                ACCUMULATE(_B,1) is [[1, 3, 3],[7, 3,  9]]"""
    min_args=1
    max_args=3
    name='ACCUMULATE'
    opcode=439
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        if isinstance(dargs[0],_NP.ndarray):
            if len(dargs)==1 or dargs[1] is None:
                ans=self.makeData(type(dargs[0].flat[0])(_NP.add.accumulate(dargs[0].flat).reshape(dargs[0].shape)))
            else:
                ans=self.makeData(type(dargs[0].flat[0])(_NP.add.accumulate(dargs[0],int(dargs[1]))))
            if hasattr(args[0],'_units'):
                ans.setUnits(args[0]._units)
            if isinstance(args[0],_data.Signal):
                ans = _updateSignal(args[0],ans)
        else:
            raise _data.TdiException("First argument must be an array or signal of an array")
        return ans

class ACHAR(_completed):
    """      F90 Character Elemental. 
      
      The character in a specified position of the
                ASCII collating sequence. The inverse of IACHAR.

      Argument. I must be integer.

      Signals.  Same as I.
      Units...  Same as I.
      Form....  Length-one character of same shape.

      Result..  For j between 0 and 127, the result is the character in
                position j of the ASCII collating sequence; otherwise,
                the result is processor dependent. It is truncated to
                8 bits on the VAX.

      Example.  ACHAR(88) has the value 'X'.

      See also. CHAR and its inverse ICHAR for a processor-dependent."""
    min_args=1
    max_args=2
    name='ACHAR'
    opcode=35
    def _evaluate(self):
        args=self.evaluateArgs()
        def doChr(arg):
            if isinstance(arg,_data.Array):
                l=list()
                for i in arg.flat:
                    l.append(chr(int(i)))
                ans=_data.makeArray(l)
                ans.reshape(arg.shape)
            elif isinstance(arg,_data.Scalar):
                ans = _data.String(chr(int(arg)))
            elif isinstance(arg,_data.Signal):
                ans=_updateSignal(arg,doChr(arg.value.evaluate()))
            elif isinstance(arg,_data.Range):
                ans = doChr(arg.data().evaluate())
            else:
                raise _data.TdiException("Cannot perform achar on type %s\n" % (str(type(arg)),))
            if hasattr(arg,'_units'):
                ans.setUnits(arg._units)
            return ans
        return doChr(args[0])

class ACOS(_completed):
    """      F90 Mathematical Elemental. 
      
      Arccosine (inverse cosine).

      Argument. X must be real and be less than 1 in magnitude.
                Complex numbers cause an error.

      Signals.  Same as X.
      Units...  None, bad if X has units.
      Form....  Real of same shape.

      Result..  Processor approximation to arccos(X) in radians.
                It lies in the range 0 to pi, inclusive.
                Out-of-range numbers get $ROPRAND.

      Example.  ACOS(0.54030231) is 1.0, approximately."""
    min_args=1
    max_args=1
    name="ACOS"
    opcode=36
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.arccos(args[0].value))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ACOS(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ABS function: %s" % (str(type(args[0])),))
        return ans

class ACOSD(_completed):
    """      Mathematical Elemental. 
      
      Arccosine (inverse cosine) in degrees.

      Argument. X must be real and be less than 1 in magnitude.
                Complex numbers cause an error.

      Signals.  Same as X.
      Units...  None, bad if X has units.
      Form....  Real of same shape.

      Result..  Processor approximation to arccos(X) in degrees.
                It lies in the range 0 to 180.
                Out-of-range numbers get $ROPRAND.

      Example.  ACOSD(0.5) is 60.0, approximately."""
    min_args=1
    max_args=1
    name="ACOSD"
    opcode=37
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.arccos(args[0].value)/_NP.pi*180.)
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ACOSD(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ACOSD function: %s" % (str(type(args[0])),))
        return ans

class ADD(_completed):
    """      Numeric Elemental. 
      
      Add numbers.
      Usual From        A + B.
      Function Form     ADD(A,B).

      Arguments A and B must be numeric.

      Signals.  Single signal or smaller data.
      Units...  Single or common units, else bad.
      Form....  Compatible form of A and B.

      Result..  The element-by-element sum of objects A and B.
      >>>>>>>>>WARNING, integer overflow is ignored.

      Example.  [2,3,4] + 5.0 is [7.0,8.0,9.0]."""
    min_args=2
    max_args=2
    name='ADD'
    syntax='arg0 + arg1'
    opcode=38
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
#        if isinstance(dargs[0],_NP.ndarray) and isinstance(dargs[1],_NP.ndarray) and (len(dargs[0]) != len(dargs[1])):
        ans=dargs[0]+dargs[1]
        units=(UNITS_OF(args[0]).evaluate(),UNITS_OF(args[1]).evaluate())
        if units[0].data().strip() != '':
            if  units[1].data().strip() != '':
                if units[0]==units[1]:
                    ans=self.makeData(ans).setUnits(units[0])
            else:
                ans=self.makeData(ans).setUnits(units[0])
        elif units[1].data().strip() != '':
            ans=self.makeData(ans).setUnits(units[1])
        if isinstance(args[0],_data.Signal) and not isinstance(args[1],_data.Signal):
            ans=_updateSignal(args[0],ans)
        elif isinstance(args[1],_data.Signal) and not isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[1],ans)
        else:
            ans=self.makeData(ans)
        return ans

class ADJUSTL(_completed):
    """      F90 Character Elemental. 
      
      Adjust to the left, removing leading blanks
                (and tabs) and inserting trailing blanks.

      Argument. STRING must be character.

      Signals.  Same as STRING.
      Units...  Same as STRING.
      Form....  Same as STRING.

      Result..  Same as STRING except that any leading blanks and tabs
                have been deleted and the same number of trailing blanks
                have been inserted.

      Example.  ADJUSTL('  WORD') is "WORD  "."""
    min_args=1
    max_args=1
    name='ADJUSTL'
    opcode=39
    def _evaluate(self):
        args=self.evaluateArgs()
        def doAdjustl(arg):
            if isinstance(arg,_data.Array):
                l=list()
                for i in arg.flat:
                    l.append(doAdjustl(self.makeData(i)))
                ans=_data.makeArray(l)
                ans.reshape(arg.shape)
            elif isinstance(arg,_data.Scalar):
                if isinstance(arg,_data.String):
                    ans = self.makeData(str(arg.value).lstrip().ljust(len(arg.value)))
                else:
                    ans = doAdjustl(TEXT(self.makeData(arg.value)).evaluate())
            elif isinstance(arg,_data.Signal):
                ans=_updateSignal(arg,doAdjustl(arg.value.evaluate()))
            elif isinstance(arg,_data.Range):
                ans = doAdjustl(arg.data())
            else:
                raise _data.TdiException("Cannot perform adjustl on type %s\n" % (str(type(arg)),))
            if hasattr(arg,'_units'):
                ans._units=arg._units
            return ans
        return doAdjustl(args[0])

class ADJUSTR(_completed):
    """      F90 Character Elemental. 
      
      Adjust to the right, removing trailing blanks
                (and tabs) and inserting leading blanks.

      Argument. STRING must be character.

      Signals.  Same as STRING.
      Units...  Same as STRING.
      Form....  Same as STRING.

      Result..  Same as STRING except that any trailing blanks and tabs
                have been deleted and the same number of leading blanks
                have been inserted.

      Example.  ADJUSTR('WORD  ') is "  WORD".

      See also. TRIM (non-elemental) to remove trailing blanks and tabs."""
    min_args=1
    max_args=1
    name='ADJUSTR'
    opcode=40
    def _evaluate(self):
        args=self.evaluateArgs()
        def doAdjustr(arg):
            if isinstance(arg,_data.Array):
                l=list()
                for i in arg.flat:
                    l.append(doAdjustr(self.makeData(i)))
                ans=_data.makeArray(l)
                ans.reshape(arg.shape)
            elif isinstance(arg,_data.Scalar):
                if isinstance(arg,_data.String):
                    ans = self.makeData(str(arg.value).rstrip().rjust(len(arg.value)))
                else:
                    ans = doAdjustr(TEXT(self.makeData(arg.value)).evaluate())
            elif isinstance(arg,_data.Signal):
                ans=_updateSignal(arg,doAdjustr(arg.value.evaluate()))
            elif isinstance(arg,_data.Range):
                ans = doAdjustr(arg.data())
            else:
                raise _data.TdiException("Cannot perform adjustl on type %s\n" % (str(type(arg)),))
            if hasattr(arg,'_units'):
                ans._units=arg._units
            return ans
        return doAdjustr(args[0])

class AIMAG(_completed):
    """      F90 Numeric Elemental. 
      
      Imaginary part of a complex number.

      Argument. Z must be complex.

      Signals.  Same as Z.
      Units...  Same as Z.
      Form....  Real of same shape.

      Result..  Real with the same type parameter as Z.
                If Z has the value CMPLX(x,y) the result is y.
      Example.  AIMAG(CMPLX(2.0,3.0)) is 3.0."""
    min_args=1
    max_args=1
    name='AIMAG'
    opcode=41
    def _evaluate(self):
        args=self.evaluateArgs()
        def doAimag(arg):
            if isinstance(arg,_data.Array):
                if isinstance(arg,(_data.Complex64Array,_data.Complex128Array)):
                    ans=self.makeData(arg.imag)
                else:
                    ans=Data.execute("$*0",(arg,))
            elif isinstance(arg,_data.Scalar):
                if isinstance(arg,(_data.Complex64,_data.Complex128)):
                    ans=self.makeData(arg.imag)
                else:
                    ans=type(arg)(0)
            elif isinstance(arg,_data.Signal):
                ans = _updateSignal(arg,doAimag(arg.value.evaluate()))
            elif isinstance(arg,_data.Range):
                ans = doAimag(arg.data())
            else:
                raise _data.TdiException("Cannot perform aimag on type %s\n" % (str(type(arg)),))
            if hasattr(arg,'_units'):
                ans.setUnits(arg._units)
            return ans
        return doAimag(args[0])

class AINT(_completed):
    """      F90 Numeric Elemental. 
      
      Trunctation to a whole number.

      Argument. Optional: KIND.
        A       real. Complex numbers are an error.
        KIND    scalar integer type number, for example, KIND(1d0).

      Signals.  Same as A.
      Units...  Same as A.
      Form....  Same as A.

      Result..  Type is KIND if it is present, else that of A.
                If |A|<1, AINT(A) is 0; else AINT is largest integer
                that does not exceed the magnitude of A and whose sign
                is that of A. Overflow is not detected.

      Examples. AINT(2.783) is 2.0. AINT(-2.783) is -2.0.

      See also. INT for integer result and BYTE, WORD, LONG, QUADWORD,
                OCTAWORD, and UNSIGNED_BYTE, etc., for specific forms.
                ANINT and NINT for rounded integral value.
		FLOOR and CEILING."""
    min_args=1
    max_args=2
    name='AINT'
    opcode=42
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            if len(self.args) == 2:
                newtype=_dtypes.mdsdtypes(int(self.args[1])).toNumpy()
            else:
                try:
                    newtype=type(self.args[0]._value[0])
                except:
                    newtype=type(self.args[0]._value)
            if hasattr(args[0],'_units'):
                ans = self.makeData(newtype(_NP.int64(args[0]._value))).setUnits(args[0]._units)
            else:
                ans = self.makeData(newtype(_NP.int64(args[0]._value)))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],AINT(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for AINT function: %s" % (str(type(args[0])),))
        return ans


class ALL(_completed):
    """      F90 Transformation. 
      
      Determine if all values are true in MASK along
                dimension DIM.

      Arguments Optional: DIM.
        MASK    logical array.
        DIM     integer scalar from 0 to n-1, where n is rank of MASK.

      Signals.  None.
      Units...  None.
      Form....  Logical. It is scalar if DIM is absent or MASK is a
                vector; otherwise, the result is an array of rank n-1
                and of shape like MASK's with DIM subscript omitted.

      Result.
        (i)     ALL(MASK) is $TRUE if all elements of MASK are true or
                if MASK has size zero and is $FALSE if any element of
                MASK is false.
        (ii)    For a vector MASK, ALL(MASK,DIM) is equal to ALL(MASK).
                Otherwise, the value of an element of the result is
                ALL of the elements of MASK varying the DIM subscript.

      Examples.
        (i)     ALL([$TRUE,$FALSE,$TRUE]) is $FALSE.
        (ii)    If _B=[[1, 3, 5],[2, 4, 6]] and 
	       _C=[[0, 3, 5],[2, 4, 6],[7, 4, 8]]
                ALL(_B NE _C,0) is [$FALSE,$FALSE,$FALSE].
                ALL(_B NE _C,1) is [$FALSE,$FALSE].

      See also. ANY for logical or, COUNT for the number of trues."""
    min_args=1
    max_args=2
    name='ALL'
    opcode=43
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        if len(dargs) == 1:
          return _data.Uint8((dargs[0]&1).all())
        else:
          dim=int(args[1])
          return _data.Uint8((dargs[0]&1).all(dim))

class ALLOCATED(_toBeCompleted):
    """      F90 Variable Inquiry. 
      
      Indicate if a variable is currently allocated.

      Argument. NAME must be a variable name or a text string.

      Signals.  None.
      Units...  None.
      Form....  Logical scalar.

      Result..  $TRUE if NAME is currently allocated, otherwise $FALSE.

      Example.  ALLOCATED(_Not_in use) is $FALSE unless it has appeared
                on the left side of an assignment expression.

      See also. DEALLOCATE to remove names and RESET_PRIVATE or
                RESET_PUBLIC for more drastic actions."""
    min_args=1
    max_args=1
    name='ALLOCATED'
    opcode=44

class AND(_completed):
    """      Logical Elemental. 
      
      Logical intersection of elements.
      Usual Forms       L && M, L AND M.
      Function Form     AND(L,M).

      Arguments L and M must be logical (lowest bit is 1 for true).

      Signals.  Single signal or smaller data.
      Units...  None unless both have units and they don't match.
      Form....  Logical of compatible shape.

      Result..  True if both are true; otherwise, false.
      >>>>>>>>>WARNING, do not confuse with & which is bit-wise IAND.

      Example.  [0,0,1,1] && [0,1,0,1] is [$FALSE,$FALSE,$FALSE,$TRUE].
      See also. EQV, NAND, NEQV, NOR, OR, and others like AND_NOT for
                other logical functions."""
    min_args=2
    max_args=2
    name='AND'
    syntax='arg0 && arg1'
    opcode=45
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        ans=(_NP.uint8(dargs[0])&1)+(_NP.uint8(dargs[1])&1==1)==2
        if isinstance(args[0],_data.Signal) and not isinstance(args[1],_data.Signal):
            ans=_updateSignal(args[0],ans)
        elif isinstance(args[1],_data.Signal) and not isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[1],ans)
        else:
            ans=self.makeData(ans)
        return ans

class AND_NOT(_completed):
    """      Logical Elemental. 
      
      Logical intersection with negation of second.
      Accepted Form. L AND_NOT M.

      Arguments L and M must be logical (lowest bit is 1 for true).

      Signals.  Single signal or smaller data.
      Units...  None unless both have units and they don't match.
      Form....  Logical of compatible shape.

      Result..  True if L is true and M is false; otherwise, false.

      Example.  [0,0,1,1] AND_NOT [0,1,0,1] is
                [$FALSE,$FALSE,$TRUE,$FALSE]."""
    min_args=2
    max_args=2
    name='AND_NOT'
    CCodeName='AndNot'
    opcode=46
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        ans=_NP.logical_and(dargs[0],_NP.logical_not(dargs[1]))
        if isinstance(args[0],_data.Signal) and not isinstance(args[1],_data.Signal):
            ans=_updateSignal(args[0],ans)
        elif isinstance(args[1],_data.Signal) and not isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[1],ans)
        else:
            ans=self.makeData(ans)
        return ans


class ANINT(_completed):
    """      F90 Numeric Elemental. 
      
      Nearest whole number.

      Argument. Optional: KIND.
        A       real. Complex numbers are an error.
        KIND    scalar integer type number, for example, KIND(1d0).

      Signals.  Same as A.
      Units...  Same as A.
      Form....  Same as A.

      Result..  Type is KIND if it is present, else that of A.
                If A>0, ANINT(A) is AINT(A+0.5); else, ANINT(A) is
                AINT(A-0.5).

      Examples. ANINT(2.783) is 3.0. ANINT(-2.783) is -3.0.

      See also. NINT for integer and INT and AINT for truncated results."""
    min_args=1
    max_args=2
    name='ANINT'
    opcode=47
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            if len(self.args) == 2:
                newtype=_dtypes.mdsdtypes(int(self.args[1])).toNumpy()
            else:
                try:
                    newtype=type(self.args[0]._value[0])
                except:
                    newtype=type(self.args[0]._value)
            if hasattr(args[0],'_units'):
                ans = self.makeData(newtype(args[0]._value.round())).setUnits(args[0]._units)
            else:
                ans = self.makeData(newtype(args[0]._value.round()))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ANINT(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for AINT function: %s" % (str(type(args[0])),))
        return ans

class ANY(_completed):
    """      F90 Transformation. 
      
      Determine whether any value is true in MASK along
                dimension DIM.

      Arguments Optional: DIM.
        MASK    logical array.
        DIM     integer scalar from 1 to n-1, where n is rank of MASK.

      Signals.  None.
      Units...  None.
      Form....  Logical. It is scalar if DIM is absent or MASK is a
                vector; otherwise, the result is an array of rank n-1
                and shaped like MASK with DIM subscript omitted.

      Result.
        (i)     ANY(MASK) is $TRUE if any elements of MASK are true and
                has $FALSE if no element is true or MASK is size zero.
        (ii)    For a vector MASK, ANY(MASK,DIM) is equal to ANY(MASK).
                Otherwise, the value of an element of the result is
                ANY of the elements of MASK varying the DIM subscript.

      Examples.
        (i)     ANY([$TRUE,$FALSE,$TRUE]) is $TRUE.
        (ii)    For 
	        _B=[[1, 3, 5],[2, 4, 6]] and 
		_C=[[0, 3, 5],[7, 4, 8]]
                ANY(_B NE _C,0) is [$TRUE,$TRUE].
                ANY(_B NE _C,1) is [$TRUE,$FALSE,$TRUE].

      See also. ALL for logical and, COUNT for the number of trues."""
    min_args=1
    max_args=2
    name='ANY'
    opcode=48
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        if len(dargs) == 1:
          return _data.Uint8((dargs[0]&1).any())
        else:
          dim=int(args[1])
          return _data.Uint8((dargs[0]&1).transpose().any(dim)) ###### transpose to match tdishr

class ARG(_completed):
    """      Mathematical Elemental. 
      
      Argument of complex number in radians.

      Argument. Z must be complex.

      Signals.  Same as Z.
      Units...  None.
      Form....  Real of same shape.

      Result..  ATAN2(AIMAG(Z),REAL(Z)).

      Example.  ARG(CMPLX(3.0,4.0)) is 0.9272952, approximately.

      See also. ABS for the complex length."""
    min_args=1
    max_args=1
    name='ARG'
    opcode=49
    def _evaluate(self):
        args=self.evaluateArgs()
        ans = ATAN2(AIMAG(args[0]),REAL(args[0])).evaluate()
        if isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ans)
        return ans

class ARGD(_completed):
    """      Mathematical Elemental. 
      
      Argument of complex number in degrees.

      Argument. Z must be complex.

      Signals.  Same as Z.
      Units...  None.
      Form....  Real of same shape.

      Result..  ATAN2D(AIMAG(Z),REAL(Z)).

      Example.  ARGD(CMPLX(3.0,4.0)) is 53.1301, approximately."""
    min_args=1
    max_args=1
    name='ARGD'
    opcode=50
    def _evaluate(self):
        args=self.evaluateArgs()
        ans = ATAN2D(AIMAG(args[0]).evaluate(),REAL(args[0]).evaluate()).evaluate()
        if isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ans)
        return ans

class ARG_OF(_completed):
    """      MDS Operation. 
      
      Get the N-th argument of a record descriptor.
                The count does not include dscptrs like image or routine.

      Arguments Optional: N.
        A       descriptor of class DSC$K_CLASS_R with arguments.
        N       integer scalar from 0 to the number of descriptors - 1.

      Result..  The N-th argument pointed to by A searched for:
                DSC$K_DTYPE_CALL
                DSC$K_DTYPE_CONDITION, the condition field.
                DSC$K_DTYPE_DEPENDENCY
                DSC$K_DTYPE_FUNCTION
                DSC$K_DTYPE_METHOD
                DSC$K_DTYPE_PROCEDURE
                DSC$K_DTYPE_ROUTINE
                Otherwise, an error.

      Example.  ARG_OF(A+B,1) is B because A+B is a FUNCTION.

      See also. DSCPTRS_OF for any descriptor."""
    min_args=1
    max_args=2
    name='ARG_OF'
    opcode=51
    def _evaluate(self):
        if isinstance(self.args[0],_data.Compound):
            if len(self.args) == 1:
                nth=0
            else:
                nth=int(self.makeData(self.args[1]).evaluate())
            if (nth + self.args[0]._argOffset + 1) > len(self.args[0].args):
                raise _data.TdiException("Argument idx (%d) exceeds number of arguments (%d)" % (nth,len(self.args[0].args)-self.args[0]._argOffset))
            elif nth < 0:
                raise _data.TdiException("Argument idx must be >= 0. Idx %d provided" % (nth,))
            return self.args[0].getArgumentAt(nth)
        else:
            raise _data.TdiException("Invalid first argument to ARG_OF() function. Must be a Compound but received a "+str(type(self.args[0]))) 
                

class ARRAY(_completed):
    """      Transformation. 
      
      Generate an uninitialized array.

      Arguments Optional: SHAPE, MOLD.
        SHAPE   integer vector.
        MOLD    any by example.
      Signals.  None.
      Units...  None.
      Form....  Type of MOLD and shape (dimensions) is SHAPE. If SHAPE
                is absent, the result is a scalar. If MOLD is absent,
                the result will be floats.

      Example.  ARRAY([2,3,4],1d0) makes an array of double precision
                reals of shape [2,3,4]. The value are not defined and
                will depend on previous memory usage.
      See also. RAMP, RANDOM, and ZERO."""
    min_args=0
    max_args=2
    name='ARRAY'
    opcode=52
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        if len(args)==0:
            ans=_data.Float32(0)
        else:
            if isinstance(args[0],_data.Array):
                if len(dargs[0]<9):
                    shape=tuple(dargs[0].tolist())
                else:
                    raise _data.TdiException("Maximum of 8 dimensions supported")
            elif dargs[0] is not None:
                raise _data.TdiException("First argument must be an array or omitted")
            else:
                shape=None
            if len(args)==1 or dargs[1] is None:
                mold=_NP.float32
            elif isinstance(args[1],_data.Scalar):
                mold=args[1].dtype
            else:
                raise _data.TdiException("Second argument must be a Scalar, an Array or omitted")
            if shape is None:
                if mold == _NP.string_:
                    ans=self.makeData('')
                else:
                    ans=self.makeData(mold(0))
            else:
                ans=self.makeData(_NP.ndarray(shape=shape,dtype=mold))
        return ans

class ASIN(_completed):
    """      F90 Mathematical Elemental. 
      
      Arcsine (inverse sine).

      Argument. X must be real and be less than or equal to 1 in
                magnitude. Complex numbers cause an error.

      Signals.  Same as X.
      Units...  None, bad if X has units.
      Form....  Real of same shape.

      Result..  Processor approximation to arcsin(X) in radians.
                It lies in the range -pi/2 to pi/2.
                Out-of-range numbers get $ROPRAND.

      Example.  ASIN(0.84147098) is 1.0, approximately."""
    min_args=1
    max_args=1
    name='ASIN'
    opcode=53
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = self.makeData(_NP.arcsin(args[0].value))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ASIN(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ABS function: %s" % (str(type(args[0])),))
        return ans

class ASIND(_completed):
    """      Mathematical Elemental. 
      
      Arcsine (inverse sine) in degrees.

      Argument. X must be real and be less than 1 in magnitude.
                Complex numbers cause an error.

      Signals.  Same as X.
      Units...  None, bad if X has units.
      Form....  Real of same shape.

      Result..  Processor approximation to arcsin(X) in degrees.
                It lies in the range -90 to 90.
                Out-of-range numbers get $ROPRAND.

      Example.  ASIND(0.5) is 30.0, approximately."""
    min_args=1
    max_args=1
    name='ASIND'
    opcode=54
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.arcsin(args[0].value)/_NP.pi*180.)
        elif isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[0],ASIND(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ACOSD function: %s" % (str(type(args[0])),))
        return ans

class AS_IS(_completed):
    """      Compile operation. 
      
      Protects the argument from one level of evaluation.

      Argument. X may be any expression and may be a NID, PATH, or
                FUNCTION.

      Result..  The argument without evaluation.

      Example.  _A = AS_IS(_B * 3.0) makes the variable _A into an
                expression. So whereever _A is used the current value of
                _B will be multiplied by three and that will be used.
                Note that _A = _B * 3.0 would have returned the then
                current value and will not change as _B does."""
    min_args=1
    max_args=1
    name='AS_IS'
    opcode=55
    def _evaluate(self):
        if isinstance(self.args[0],(_tree.TreeNode,_tree.TreePath,Builtin,_data.Ident)):
            return self.args[0]
        else:
            raise _data.TdiException("Argument must be one of: an expression, a tree node, a tree path or a variable")

class ATAN(_completed):
    """       F90 Mathematical Elemental. 
      
      Arctangent (inverse tangent).

      Argument. X must be real. Complex numbers are an error.

      Signals.  Same as X.
      Units...  None, bad if X has units.
      Form....  Real of same shape.

      Result..  Processor approximation to arctan(X) in radians.
                It lies in the range -pi/2 to pi/2, inclusive.

      Example.  ATAN(1.5574077) is 1.0, approximately."""
    min_args=1
    max_args=1
    name='ATAN'
    opcode=56
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.arctan(args[0].value))
        elif isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[0],ATAN(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ABS function: %s" % (str(type(args[0])),))
        return ans

class ATAN2(_completed):
    """      F90 Mathematical Elemental. 
      
      Arctangent (inverse tangent). The principal
                value of the argument of the nonzero complex number
                CMPLX(X,Y).

      Arguments X any Y must be real. Complex numbers are an error.

      Signals.  Single signal or smaller data.
      Units...  None unless both have units and they don't match.
      Form....  The compatible form of X and Y.

      Result..  Processor approximation to arctan(Y/X) in radians.
                It lies in the range -pi to pi.
                If Y > 0, the result is positive.

      Examples. ATAN2(1.5574077,1.0) is 1.0, approximately.
                ATAN2([ 1,  1], [-1, 1]) is [ 3*pi/4 , pi/4].
                      
      See also. ARG for the angle of a complex number."""
    min_args=2
    max_args=2
    name='ATAN2'
    opcode=57
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        for i in range(len(dargs)):
            dargs[i]=_int32ToFloat(dargs[i])
        ans = _NP.arctan2(*dargs)
        if isinstance(args[0],_data.Signal) and not isinstance(args[1],_data.Signal):
            ans=_updateSignal(args[0],ans)
        elif isinstance(args[1],_data.Signal) and not isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[1],ans)
        else:
            ans=self.makeData(ans)
        return ans

class ATAN2D(_completed):
    """      Mathematical Elemental. 
      
      Arctangent (inverse tangent) in degrees. The
                principal value of the argument of the nonzero complex
                number CMPLX(X,Y).

      Arguments X and Y must be real. Complex numbers are an error.

      Signals.  Single signal or smaller data.
      Units...  None unless both have units and they don't match.
      Form....  The compatible form of X and Y.

      Result..  Processor approximation to arctan(Y/X) in degrees.
                It lies in the range -180 to 180.
                If Y>0, the result is positive.

      Example.  ATAN2D(-1.0,-1.0) is -135.0, approximately.
                ATAN2D([ 1,  1], [-1, 1]) is [ 135. , 45.].
                         

      See also. ARGD for the angle of a complex number in degrees."""
    min_args=2
    max_args=2
    name='ATAN2D'
    opcode=58
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        for i in range(len(dargs)):
            dargs[i]=_int32ToFloat(dargs[i])
        ans = _NP.arctan2(*dargs)
        if isinstance(ans,_NP.ndarray):
            ans = type(ans[0])(ans/type(ans[0])(_NP.pi)*180)
        else:
            ans = type(ans)(ans/type(ans)(_NP.pi)*180)
        if isinstance(args[0],_data.Signal) and not isinstance(args[1],_data.Signal):
            ans=_updateSignal(args[0],ans)
        elif isinstance(args[1],_data.Signal) and not isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[1],ans)
        else:
            ans=self.makeData(ans)
        return ans

class ATAND(_completed):
    """      Mathematical Elemental. 
      
      Arctangent (inverse tangent) in degrees.

      Argument. X must be real and be less than 1 in magnitude.
                Complex numbers cause an error.

      Signals.  Same as X.
      Units...  None, bad if X has units.
      Form....  Real of same shape.
      Result..  Processor approximation to arctan(X) in degrees.
                It lies in the range -90 to 90.

      Example.  ATAND(1.0) is 45.0, approximately."""
    min_args=1
    max_args=1
    name='ATAND'
    opcode=59
    def _evaluate(self):
        args=self.evaluateArgs()
        darg=_int32ToFloat(_dataArg(args[0]))
        ans = _NP.arctan(darg)
        if isinstance(ans,_NP.ndarray):
            ans = self.makeData(type(ans[0])(ans/_NP.pi*180))
        else:
            ans = self.makeData(type(ans)(ans/_NP.pi*180))
        if isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[0],ans)
        return ans

class ATANH(_completed):
    """      Mathematical Elemental. 
      
      Hyperbolic arctangent (inverse tangent).

      Argument. X must be real. Complex numbers cause an error.

      Signals.  Same as X.
      Units...  None, bad if X has units.
      Form....  Real of same shape.

      Result..  Processor approximation to arctanh(X) in radians.

      Example.  ATANH(0.7615942) is 1.0, approximately."""
    min_args=1
    max_args=1
    name='ATANH'
    opcode=60
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.arctanh(args[0].value))
        elif isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[0],ATANH(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for ABS function: %s" % (str(type(args[0])),))
        return ans

class AXIS_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the axis field.

      Argument. Descriptor as below.

      Result..  A is searched for these:
                DSC$K_DTYPE_DIMENSION, the axis field.
                DSC$K_DTYPE_RANGE, the range.
                DSC$K_DTYPE_SLOPE, the slope, !deprecated!.
                Otherwise, an error.

      Example.  AXIS_OF(BUILD_DIM(BUILD_WINDOW(B,E,X0),1..10)) is 1..10."""
    min_args=1
    max_args=1
    name='AXIS_OF'
    opcode=61
    partnames=('axis','range','slope')

class BEGIN_OF(_completed):
    """      MDS Operation. 
      
      Get the begin field.

      Arguments Optional: N.
        A       as below.
        N       integer scalar, for slopes from 1 to the number of
                segments less one. The first segment has no beginning
                if the axis is infinite.

      Result..  A is searched for these:
                DSC$K_DTYPE_RANGE, the begin field (may be an array).
                DSC$K_DTYPE_SLOPE, N-th segment's begin field !deprecated!.
                DSC$K_DTYPE_WINDOW, the startidx field.
                Otherwise, an error.

      Example.  BEGIN_OF(1..10) is 1."""
    min_args=1
    max_args=2
    name='BEGIN_OF'
    opcode=64
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],(_data.Range,_data.Slope)):
            if len(args) == 1:
                ans=args[0].getBegin()
            else:
                ans=SUBSCRIPT(args[0].getBegin(),args[1]).evaluate()
        elif isinstance(args[0],_data.Window):
            ans=args[0].getStartIdx()
        else:
            raise _data.TdiException("Argument is wrong type (%s) for BEGIN_OF() function" % (str(type(args[0])),))
        return ans

class BIT_SIZE(_completed):
    """      F90 Inquiry. 
      
      The length of integer or other type (extension) in bits.

      Argument. I is any type, scalar or array.

      Signals.  None.
      Units...  None.
      Form....  Integer scalar.

      Result..  The number of bits in I if it is scalar or in
                an element of I if it is an array.

      Example.  BIT_SIZE(1) is 32."""
    min_args=1
    max_args=1
    name='BIT_SIZE'
    opcode=411
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            return _data.Int32(args[0].itemsize*8)
        else:
            raise _data.TdiException("Wrong argument type (%s) provided to BIT_SIZE() function" % (str(type(args[0])),))

class BREAK(_toBeCompleted):
    """      CC Statement. 
      
      Break from FOR or WHILE loops or SWITCH.
      Usual Form        BREAK;
      Function Form     BREAK(). May be syntatically invalid.

      Arguments None.

      Result..  None.

      Example.  FOR (_J=DSIZE(_X); --J>=0; ) IF (_X[_J]) BREAK;
                IF (_J < 0) ABORT();
                is a lousy way to do IF (!ALL(_X)) ABORT();."""
    min_args=0
    max_args=0
    name='BREAK'
    syntax='BREAK'
    opcode=66

class BSEARCH(_toBeCompleted):
    """      Numeric and Character Elemental. 
      
      Binary search in a sorted table.

      Arguments Optional: MODE.
        X       integer, real, or text, scalar or array. No complex.
        TABLE   ascending-sorted, scalar or array. Should be integer,
                real, or text.
        MODE    integer scalar, default is 0.

      Signals.  Same as X.
      Units...  None.
      Form....  Integer offset in table of match.
      Result..  The offset in TABLE whose value matches X.
                For each list element k and matching table element j:
                (1) MODE=0, TABLE[j] == X[k] with result range 0 to n-1,
                where n is the number of elements in TABLE
                or -1 if no exactly matching element number.
                (2) MODE=+1, TABLE[j] <= X[k] < TABLE[j+1]
                with result range -1 to n.
                (3) MODE=-1, TABLE[j-1] < X[k] < TABLE[j]
                with result range 0 to n+1.
                Effectively, TABLE[-1] is negative infinity and TABLE[n]
                is positive infinity.

      Examples. BSEARCH(3,1:10) is 2.
                BSEARCH(1..8,3..5) is [-1,-1,0,1,2,-1,-1,-1].
                MAP(1:10,BSEARCH(3.9,1:10,1)) is 3.

      See also. SORT and SORTI for data and index sorting.
                MAP to pick the selected elements."""
    min_args=2
    max_args=4
    name='BSEARCH'
    opcode=67

class BTEST(_completed):
    """      F90 Bit-wise Elemental. 
      
      Test a bit of a number.

      Arguments
        I       any. F90 requires integer.
        POS     integer offset within the element of I. Must be
                nonnegative and less than BIT_SIZE(I).

      Signals.  Same as I.
      Units...  Same as I.
      Form....  Logical of compatible shape.

      Result..  True if POS is proper and the element is 1;
                otherwise, false.

      Examples. BTEST(8,3) is $TRUE. if _A = Set_range(2,2,[1,3,2,4])
                BTEST(_A,2) is
                Set_Range(2,2,[$FALSE,$FALSE,$FALSE,$TRUE]).
                BTEST(2,_A) is
                Set_Range(2,2,[$TRUE,$FALSE,$FALSE,$FALSE]).

      See also. IBCLR to clear, BITS to extract, and IBSET to set."""
    min_args=2
    max_args=2
    name='BTEST'
    opcode=69
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        if dargs[1].dtype.kind!='i':
            raise _data.TdiException("position must be an integer scalar or array")
        if (dargs[1]<0).any() or (dargs[1]>=dargs[0].itemsize*8).any():
            raise _data.TdiException("position must be between 0 and %d" % (dargs[0].itemsize*8-1,))
        mask=1<<dargs[1]
        ans=_NP.uint8(_NP.bitwise_and(dargs[0],mask)!=0)
        units=UNITS_OF(args[0]).evaluate()
        if units.data().strip() != '':
            ans=self.makeData(ans).setUnits(units)
        if isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[0],self.makeData(ans))
        else:
            ans=self.makeData(ans)
        return ans

class _BUILD_XXX(_completed):
    def _evaluate(self):
        args=list(self.args)
        args.insert(0,self.name+'('+','.join('$'*len(self.args))+')')
        return COMPILE(*args).evaluate()

class BUILD_ACTION(_BUILD_XXX):
    """      MDS Operation. 
      
      Make an action descriptor.

      Arguments
        DISPATCH dispatch descriptor.
        TASK    procedure, program, routine, or method descriptor.
        ERRORLOGS a character scalar for error reports.
        COMPLETION notification list.
        PERFORMANCE unsigned long vector of statistics from execution.

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.

      Example.  BUILD_ACTION(BUILD_DISPATCH("ident","phase","when",
                "completion"),BUILD_ROUTINE(timeout,image,routine))
                has only dispatch and task."""
    min_args=2
    max_args=5
    name='BUILD_ACTION'
    opcode=70

class BUILD_CALL(_BUILD_XXX):
    """      MDS Operation. 
      
      Make a call of a routine in a sharable image.
      Usual Forms       IMAGE->ROUTINE:KIND([ARG],...) or IMAGE->ROUTINE([ARG])

      Arguments Optional: KIND, ARG... .
        KIND    byte unsigned scalar of KIND returned in R0.
                Use DSC$K_DTYPE_DSC=24 for a pointer to an XD.
                Use DSC$K_DTYPE_MISSING=0 for no information.
                Default type is long integer.
                Other accepted types are BU WU LU QU OU B W L Q O F D
                NID and null-terminated strings T PATH EVENT.
        IMAGE   character scalar. It must be a simple filename in
                SYS$SHARE or a logical name of the file.
        ROUTINE character scalar.
        ARG...  arguments with certain options.

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.
                Use this form if IMAGE or ROUTINE must be expressions.

      Example.  BUILD_CALL(24,'TDISHR','TDI$SIND',DESCR(30.)) is
                the slow and hard way to do SIND(30.).

      See also. CALL for info on argument form and type of output."""
    min_args=3
    max_args=254
    name='BUILD_CALL'
    opcode=397

class BUILD_CONDITION(_BUILD_XXX):
    """      MDS Operation. 
      
      Make a condition descriptor.OBSOLETE. NO LONGER SUPPORTED.

      Arguments
        MODIFIER word unsigned, evaluated:
                TREE$K_NEGATE_CONDITION 7
                TREE$K_IGNORE_UNDEFINED 8
                TREE$K_IGNORE_STATUS    9
        CONDITION MDS event or path.

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.

      Example.  None, normally done by COMPILE_DEPENDENCY.

      See also. BUILD_DEPENDENCY BUILD_EVENT and COMPILE_DEPENDENCY."""
    min_args=2
    max_args=2
    name='BUILD_CONDITION'
    opcode=71

class BUILD_CONGLOM(_BUILD_XXX):
    """      MDS Operation.
      
      Make a conglomerate descriptor.

      Arguments
        IMAGE   character scalar.
        MODEL   character scalar.
        NAME    character scalar.
        QUALIFIERS long vector, module dependent.

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.

      Example.  None, normally done by module add routines."""
    min_args=4
    max_args=4
    name='BUILD_CONGLOM'
    opcode=72

class BUILD_DEPENDENCY(_BUILD_XXX):
    """      MDS Operation.
      
      Make a dependency descriptor.

      Arguments
        OP_CODE word unsigned scalar, evaluated.
                TREE$K_DEPENDENCY_AND   10
                TREE$K_DEPENDENCY_OR    11
        ARG_1   MDS condition, event, or path.
        ARG_2   MDS condition, event, or path.

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.
      Example.  None, normally done by COMPILE_DEPENDENCY.

      See also. BUILD_CONDITION BUILD_EVENT and COMPILE_DEPENDENCY."""
    min_args=3
    max_args=3
    name='BUILD_DEPENDENCY'
    opcode=73

class BUILD_DIM(_BUILD_XXX):
    """      MDS Operation.
      
      Make a dimension descriptor.

      Arguments Optional: WINDOW.
        WINDOW  window descriptor.
                If missing, all point of AXIS are included and
                the initial point of the axis has an index of 0.
        AXIS    slope or, if defined, other descriptor type.

      Signals.  None.
      Units...  From AXIS. Should be same as WINDOW's value_at_idx0.
      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.
                The array will have bounds only if the
                window has a defined value at index 0.

      Example.  BUILD_DIM(BUILD_WINDOW(-1,3,10.),BUILD_SLOPE(3.))
                makes dimension with value
                SET_RANGE(-1..3, [7.,10.,13.,16.,19.])."""
    min_args=2
    max_args=2
    name='BUILD_DIM'
    opcode=74

class BUILD_DISPATCH(_BUILD_XXX):
    """      MDS Operation.
      
      Make a dispatch descriptor.

      Arguments
        TYPE    byte unsigned scalar, evaluated:
                TREE$K_SCHED_ASYNC      1
                TREE$K_SCHED_SEQ        2
                TREE$K_SCHED_COND       3
        IDENT   character scalar.
        PHASE   character scalar.
        WHEN    character scalar?
        COMPLETION character scalar?

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.

      Example.  None, normally done by module add routine."""
    min_args=5
    max_args=5
    name='BUILD_DISPATCH'
    opcode=75

class BUILD_EVENT(_BUILD_XXX):
    """      MDS Operation.
      
      Make an event descriptor.

      Argument. STRING must be a character scalar expression.

      Result..  Class-S, data type-EVENT descriptor.
                Immediate at compilation.

      Example.  BUILD_EVENT('SHOT_DONE') makes an event for use in other
                descriptors.

      See also. BUILD_CONDITION BUILD_DEPENDENCY and COMPILE_DEPENDENCY."""
    min_args=1
    max_args=1
    name='BUILD_EVENT'
    opcode=76

class BUILD_FUNCTION(_completed):
    """      MDS Operation.
      
      Make a function descriptor.

      Arguments Optional: ARG,... .
        OPCODE  unsigned word from 0 to the number defined less one.
        ARG,... as needed by the function described by OPCODE.

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.
      Example.  BUILD_FUNCTION(BUILTIN_OPCODE('SIN'),30) makes an
                expression SIN(30)."""
    min_args=1
    max_args=254
    name='BUILD_FUNCTION'
    opcode=77
    def _evaluate(self):
        try:
            opcode=int(self.args[0])
        except:
            raise _data.TdiException("Unable to convert first argument to an integer")
        return Builtin(opcode,self.args[1:])

class BUILD_METHOD(_BUILD_XXX):
    """      MDS Operation.
      
      Make a method descriptor. 
 
      Arguments Optional: ARG,... . 
        TIME_OUT real scalar. 
        METHOD  character scalar. 
        OBJECT  character scalar. 
        ARG,... as needed by METHOD applied to OBJECT. 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by module add routine."""
    min_args=3
    max_args=254
    name='BUILD_METHOD'
    opcode=78

class BUILD_OPAQUE(_BUILD_XXX):
    """      MDS Operation. 
      
      Construct an Opaque object consisting of a byte array and a description string.
      Usual Forms       BUILD_OPAQUE(ARRAY,STRING)

      Arguments:
        ARRAY   byte unsigned array
        STRING  text to indicate the format of the array (i.e. mpeg,gif,jpeg)

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.

      Example.  BUILD_OPAQUE([32bu,40bu,41bu,...],'jpeg')
                Store a jpeg image in an MDSplus node. The MDSplus python
                module provides an image method for Opaque objects which
                uses the Image python module to examine the bytes
                and determine the Image type contained in the bytes.

                A series of Opaque objects can be stored as individual
                segments in a tree node."""
    min_args=2
    max_args=2
    name='BUILD_OPAQUE'
    opcode=454

class BUILD_PARAM(_BUILD_XXX):
    """      MDS Operation.
      
      Make a parameter descriptor. 
 
      Arguments 
        VALUE   any. 
        HELP    character. Textual information about VALUE. 
        VALIDATION logical scalar. $VALUE may be used by VALIDATION to 
                test VALUE without explicit reference to a tree path. 
                $THIS will give the parameter descriptor itself. 
                $VALUE and $THIS may only be used within GET_DATA 
                evaluations of the arguments. 
      >>>>>>>>>WARNING Use of $THIS and $VALUE may be infinitely recursive. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  BUILD_PARAM(42.0,'The answer.', 
                $VALUE > 6 && HELP_OF($THIS) <> ""). 
                DATA(above) is 42.0 and VALIDATION(above) is 1BU."""
    min_args=3
    max_args=3
    name='BUILD_PARAM'
    opcode=79

class BUILD_PATH(_completed):
    """      MDS Operation.
      
      Make a path (tree location) descriptor. 
 
      Argument. STRING must be a character scalar expression. 
 
      Result..  Class-S, data type-PATH descriptor. 
                Immediate at compilation. 
 
      Example.  BUILD_PATH('\TOP.XRAY:LEADER') makes a path that can be 
                evaluated."""
    min_args=1
    max_args=1
    name='BUILD_PATH'
    opcode=80
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],(_data.String,str)):
            name=str(args[0]).strip()
            if len(name) > 1 and name[0:2]=='\\\\':
                name=name[1:]
            ans = _tree.TreePath(name)
        else:
            raise _data.TdiException("Invalid argument provided, must be a string but got %s" % (str(type(args[0])),))
        return ans

class BUILD_PROCEDURE(_BUILD_XXX):
    """      MDS Operation.
      
      Make a procedure call 
 
      Arguments Optional: ARG,... . 
        TIME_OUT real scalar. 
        LANGUAGE character scalar. The language in which the procedure 
                is written. 
        PROCEDURE character scalar. 
        ARG,... as needed by the procedure. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by module add routine. """
    min_args=3
    max_args=254
    name='BUILD_PROCEDURE'
    opcode=81

class BUILD_PROGRAM(_BUILD_XXX):
    """      MDS Operation.
      
      Make a procedure call 
 
      Arguments Optional: ARG,... . 
        TIME_OUT real scalar. 
        LANGUAGE character scalar. The language in which the procedure 
                is written. 
        PROCEDURE character scalar. 
        ARG,... as needed by the procedure. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by module add routine."""
    min_args=2
    max_args=2
    name='BUILD_PROGRAM'
    opcode=82

class BUILD_RANGE(_BUILD_XXX):
    """      MDS Operation.
      
      Make a range descriptor. 
      
      Usual Form        START .. END [.. DELTA] or START : END [: DELTA]. 
 
      Arguments Optional: DELTA; START and END when used as subscript 
                limits. See the specific routine; otherwise, required. 
        START   scalar. The starting value. 
        END     scalar. The last value. 
        DELTA   scalar. The increment. Default is one. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
                This uses a data type RANGE, whereas 
                DTYPE_RANGE(START,END,DELTA) is a function. 
                On evaluation, the compatible data type. 
                A vector of length max((END - BEGIN)/DELTA,0) elements. 
 
                The first value will be BEGIN and successive values will 
                differ by DELTA. The last value will not be futher from 
                BEGIN than END. 
      >>>>>>>>>WARNING, the number of element cannot always be predicted 
                for fractional delta, 1:2:.1 may have 10 or 11 elements. 
      >>>>>>>>>WARNINGS, the colon (:) form may be confused with a tree member 
                and the dot-dot (..) form is hard to read/understand, 
                use spaces. 
 
      Examples. 2..5 becomes [2,3,4,5] and 2:5:1.8 becomes [2.,3.8]."""
    min_args=2
    max_args=3
    name='BUILD_RANGE'
    opcode=83

class BUILD_ROUTINE(_BUILD_XXX):
    """      MDS Operation.
      
      Make a routine descriptor. 
 
      Arguments Optional: ARG,... . 
        TIME_OUT real scalar. 
        IMAGE   character scalar. 
        ROUTINE character scalar. 
        ARG,... as needed by the routine. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  BUILD_ROUTINE(1.2,MYIMAGE,MYROUTINE,5)."""
    min_args=3
    max_args=254
    name='BUILD_ROUTINE'
    opcode=84

class BUILD_SIGNAL(_BUILD_XXX):
    """      MDS Operation.
      
      Make data with dimensions. 
 
      Arguments Optional: DIMENSION,... . 
        DATA    any expression. It may include $VALUE for RAW without a 
                tree reference or $THIS to refer to the whole signal. 
                $VALUE and $THIS may only be used within GET_DATA 
                evaluations of the signal. 
      >>>>>>>>>WARNING Use of $THIS and $VALUE may be infinitely recursive. 
        RAW     any expression. Usually the actual stored integer data. 
        DIMENSION,... dimension descriptor. The number of dimension 
                descriptors must match rank of DATA. 
      >>>>>>>>>WARNING, if the dimension is not of data type dimension, then 
                subscripting is by index value and not axis value. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  BUILD_SIGNAL(BUILD_WITH_UNITS($VALUE*6,'m/s^2'), 
                BUILD_WITH_UNITS(5./1024*[1,2,3],'V'), 
                BUILD_DIMENSION(BUILD_WINDOW(0,2,10.), 
                BUILD_SLOPE(BUILD_WITH_UNITS(3.,'s')))) 

   NOTE: Use BUILD_xxx for immediate structure building. (From Build_Call.)
	 Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.
	 Use this form if IMAGE or ROUTINE must be expressions."""
    min_args=2
    max_args=10
    name='BUILD_SIGNAL'
    opcode=85

class BUILD_SLOPE(_BUILD_XXX):
    """MDS Operation.
      
      Make a piece-wise linear slope-axis for dimension. 
      >>>>>>>>>WARNING, this is a deprecated feature and there is no assurance 
                of future support. 

      Arguments Optional: BEGIN, END, and more segments. 
        SLOPE   real scalar. Ratio of change of axis to change of index. 
        BEGIN   real scalar. Axis starting point. 
        END     real scalar. Axis ending point, the last value. 
 
                Note. The axis may be divided into multiple segments. 
                Without a window ISTART, there must be a first BEGIN. 
                If the slope is used in a dimension with a window,  then 
                the greater of the window's ISTART or the first BEGIN is 
                used and the lesser of the window's IEND or the last END 
                is used, assuming positive slope. 
 
      Signals.  None. 
      Units...  Combined from SLOPE and BEGIN. END units are combined 
                from the first segment if no BEGIN is applied. 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Examples. BUILD_SLOPE(3.0) is a constant ratio of 3 axis values 
                per index step. Axes can be infinite in extent. 
                A finite axis of BUILD_SLOPE(3,12,21) has data points 
                [12,15,18,21]. 
                BUILD_SLOPE(3.0,,10.,4.0,20.0) has points at 
                ...,4.0,7.0,20.0,24.0,28.0,... . Note that the dead zone 
                from 10 to 20 is absent and that thus 10.0 becomes 20.0. 
                Often BEGIN[j+1] is the same as END[j] + SLOPE[j] as in 
                a clock that does not stop but does change rate."""
    min_args=1
    max_args=254
    name='BUILD_SLOPE'
    opcode=86

class BUILD_WINDOW(_BUILD_XXX):
    """      MDS Operation.
      
      Make a window descriptor for a dimension. 
 
      Arguments Optional: ISTART, IEND, X_AT_0. 
        ISTART  integer scalar. First element stored. 
        IEND    integer scalar. Last element stored. 
        X_AT_0  real scalar. Value at index zero. 
                The effective defaults are -HUGE(1), +HUGE(1), and zero. 
                If missing completely, the beginning of the axis is 
                used for X_AT_0 when evaluating a dimension. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  BUILD_WINDOW(-1024,7168,BUILD_WITH_UNIT(-0.1,'s'))"""
    min_args=3
    max_args=3
    name='BUILD_WINDOW'
    opcode=87

class BUILD_WITH_ERROR(_BUILD_XXX):
    """      MDS Operation.
      
      Make a data with error structure. 
 
      Arguments 
        DATA    any expression that DATA(this) will be valid. 
        ERROR   Error value. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example:

          _A0 = Build_With_Error(52.9177E-12, 2400E-21)"""
    min_args=2
    max_args=2
    name='BUILD_WITH_ERROR'
    opcode=445

class BUILD_WITH_UNITS(_BUILD_XXX):
    """      MDS Operation.
      
      Make a describe data with units. 
 
      Arguments 
        DATA    any expression that DATA(this) will be valid. 
        UNITS   character string. See the primary section on "Units". 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  _S = BUILD_WITH_UNITS($VALUE*6,'m/s^2') can be used in a 
                BUILD_SIGNAL(_S,BUILD_WITH_UNITS(5./1024*raw_node,'V') 
                or similar. Note this could also have been 
                BUILD_WITH_UNITS(BUILD_SIGNAL($VALUE*6, 
                BUILD_WITH_UNITS(5./1024*raw_node,'V')),'m/s^2')."""
    min_args=2
    max_args=2
    name='BUILD_WITH_UNITS'
    opcode=88

class BUILTIN_OPCODE(_completed):
    """      MDS Character Elemental.
      
      Convert string to a builtin value. 
 
      Argument. STRING must be character. 
 
      Signals.  Same as STRING. 
      Units...  None, bad if STRING has units. 
      Form....  Unsigned word of same shape. 
 
      Result..  The number associated with the builtin name. 
                Builtin names are like "BUILTIN_OPCODE". 
 
      Example.  BUILTIN_OPCODE('$') is 0."""
    min_args=1
    max_args=1
    name='BUILTIN_OPCODE'
    opcode=89
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.String):
            bname=str(args[0]).upper().strip()
            if bname in Builtin.builtins_by_name:
                return _data.Int16(Builtin.builtins_by_name[bname].opcode)
            else:
                raise _data.TdiException("No builtin called %s" % bname)
        else:
            raise _data.TdiException("Argument must be a string. got %s" % (str(type(args[0])),))

class BYTE(_completed):
    """      Conversion Elemental.
      
      Convert to one byte integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Byte-length integer of same shape. 
 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. BYTE(123) is 123B. BYTE(257) is 1B."""
    min_args=1
    max_args=1
    name='BYTE'
    opcode=90
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        if isinstance(dargs[0],_NP.ndarray):
            ans=self.makeData(_NP.array(dargs[0],dtype=_NP.int8))
        else:
            ans=self.makeData(_NP.int8(dargs[0]))
        units=UNITS_OF(args[0]).evaluate()
        if units.data().strip() != '':
            ans=ans.setUnits(units)
        if isinstance(args[0],_data.Signal):
                ans = _updateSignal(args[0],ans)
        return ans

class BYTE_UNSIGNED(_completed):
    """      Conversion Elemental.
      
      Convert to one byte unsigned integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Byte-length unsigned integer of same shape. 
 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. BYTE_UNSIGNED(123) is 123BU. BYTE_UNSIGNED(257) is 1BU."""
    min_args=1
    max_args=1
    name='BYTE_UNSIGNED'
    opcode=91
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        if isinstance(dargs[0],_NP.ndarray):
            ans=self.makeData(_NP.array(dargs[0],dtype=_NP.uint8))
        else:
            ans=self.makeData(_NP.uint8(dargs[0]))
        units=UNITS_OF(args[0]).evaluate()
        if units.data().strip() != '':
            ans=ans.setUnits(units)
        if isinstance(args[0],_data.Signal):
                ans = _updateSignal(args[0],ans)
        return ans

class CASE(_toBeCompleted):
    """      CC-F90 Modified Statement. 
      
      Do statement if SWITCH test matches value. 
      Required Usual Form       CASE (X) STMT. 
      >>>>>>>>>WARNING, the parentheses are required here, unlike in C. 
                Note F90 uses SELECT CASE (X) ... END CASE. 
      Function Form     CASE(X,STMT,...). May be syntatically invalid. 
 
      Arguments 
        X       any comparison scalar or scalar range. 
                The range must not be stepped but may be open ended. 
                For example, 4, 4:, :6, and 4..6 are acceptable. 
        STMT    statement simple or {compound} or multiple. 
 
      Result..  None. 
 
      Example.  SWITCH (_k) { 
                CASE (1) _j=_THING1; BREAK; 
                CASE (4.5:5.5) _j=_OTHER_THING; BREAK; 
                CASE DEFAULT ABORT(); 
                }."""
    min_args=2
    max_args=254
    name='CASE'
    opcode=92

class CEILING(_completed):
    """      F90 Numeric Elemental. 
      
      The smallest whole number not below the argument. 
 
      Argument. A must be integer or real. Complex numbers are an error. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Same as A. 
 
      Result..  For integral A, no change. AINT(A) if A>0, A if A<0 and 
                A==AINT(A), else AINT(A)-1. 
 
      Examples. CEILING(2.783) is 3.0. CEILING(-2.783) is -2.0."""
    min_args=1
    max_args=1
    name='CEILING'
    opcode=93
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        ans=self.makeData(_NP.ceil(dargs[0]))
        units=UNITS_OF(args[0]).evaluate()
        if units.data().strip() != '':
            ans=ans.setUnits(units)
        if isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ans)
        return ans

class CHAR(_completed):
    """      F90 Character Elemental. 
      
      The character in a specified position of the 
                processor collating sequence. The inverse of the ICHAR. 
 
      Argument. Optional: KIND. 
        A       integer. 
        KIND    scalar integer type number, for example, KIND(' '). 
                (Today only one text type is supported.) 
 
      Signals.  Same as I. 
      Units...  Same as I. 
      Form....  Length-one character of same shape. 
 
      Result..  Type KIND if it is present, else character. 
                The character in position I of the processor collating 
                sequence. ICHAR(CHAR(I)) is I for 0<=I<=n-1 and 
                CHAR(ICHAR(C)) is C for any representable character. 
                It is truncated to 8 bits on the VAX. 
 
      Example.  CHAR(88) has the value 'X' on the VAX."""
    min_args=1
    max_args=2
    name='CHAR'
    opcode=94
    def _evaluate(self):
      args=self.evaluateArgs()
      dargs=_dataArgs(args)
      ans=_NP.uint8(dargs[0]).tostring()
      if len(dargs[0].shape) > 0:
        arr=list()
        for i in ans:
          arr.append(i)
        ans = _NP.array(arr).reshape(dargs[0].shape)
      ans=_data.makeData(ans)
      units=UNITS_OF(args[0]).evaluate()
      if units.data().strip() != '':
        ans=ans.setUnits(units)
      if isinstance(args[0],_data.Signal):
        ans = _updateSignal(args[0],ans)
      return ans

class CLASS(_completed):
    """      MDS/VMS Operation. 
      
      Class of data storage descriptor. 
 
      Argument. A may be any descriptor. 
 
      Result..  Byte unsigned of the descriptor class. 
                Descriptor data types (DSC$K_DTYPE_DSC) are removed. 
                Use CLASS for data class without NID, PATH, or variable. 
                Use CLASS_OF for data class including them. 
 
      Examples. CLASS(3) is 1BU (DSC$K_CLASS_S) and 
                CLASS([]) is 4BU (DSC$K_CLASS_A). 
                CLASS(_A) is the class of the value in variable _A."""
    min_args=1
    max_args=1
    name='CLASS'
    opcode=95
    def _evaluate(self):
      arg=self.evaluateArgs()[0]
      if hasattr(arg,'_units') or hasattr(arg,'_error'):
        mdsclass=_data.Compound.mdsclass
      else:
        mdsclass=arg.mdsclass
      return _data.Uint8(mdsclass)

class CLASS_OF(_completed):
    """      MDS/VMS Operation. 
      
      Class of data storage descriptor. 
 
      Argument. A may be any descriptor. 
 
      Result..  Byte unsigned of the descriptor class. 
                Descriptor data types (DSC$K_DTYPE_DSC) are removed. 
                Use CLASS for data class without NID, PATH, or variable. 
                Use CLASS_OF for data class including them. 
 
      Examples. CLASS_OF(3) is 1BU (DSC$K_CLASS_S) and 
                CLASS_OF([]) is 4BU (DSC$K_CLASS_A). 
                CLASS(_A) is 1BU (DSC$K_CLASS_S)."""
    min_args=1
    max_args=1
    name='CLASS_OF'
    opcode=435
    def _evaluate(self):
      if hasattr(self.args[0],'_units') or hasattr(self.args[0],'_error'):
        mdsclass=_data.Compound.mdsclass
      else:
        mdsclass=args[0].mdsclass
      return _data.Uint8(mdsclass)

class CMPLX(_completed):
    """      F90 Conversion Elemental. 
      
      Convert to complex type. 
 
      Arguments Optional: Y, KIND. 
        X       numeric. 
        Y       numeric. Default is zero. 
        KIND    scalar integer type number, for example, KIND(1d0). 
                Default is compatible form of X and Y. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Complex. If KIND present, the complex type KIND; 
                otherwise, the complex type of X and Y. 
                The compatible shape of X and Y. 
 
      Result..  Type KIND if it is present, else complex of 
                compatible type of X and Y. 
                If Y is absent and X is not complex, it is as if Y were 
                present with value zero. If Y is absent and X is 
                complex, it is as if Y were present with the value 
                AIMAG(X). If both are present, the real parts of X and Y 
                are used. If KIND is absent, it is ignored; otherwise, 
                CMPLX(X,Y,KIND) has real part REAL(X,KIND) and imaginary 
                part REAL(Y,KIND). 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. CMPLX(-3) is CMPLX(-3.0,0.0). CMPLX(3,4,5d6) is 
                CMPLX(3d0,4d0)."""
    min_args=1
    max_args=3
    name='CMPLX'
    opcode=97
    def _evaluate(self):
      args=self.evaluateArgs()
      dargs=_dataArgs(args)
      real_part=list()
      imag_part=list()
      for val in dargs[0].flat:
          if isinstance(val,_NP.float64) or (len(dargs)==3 and isinstance(dargs[2],_NP.float64)):
            real_part.append(_NP.float64(val))
          else:
            real_part.append(_NP.float32(val))
      if len(dargs)>1:
        for val in dargs[1].flat:
          if isinstance(val,_NP.float64) or (len(dargs)==3 and isinstance(dargs[2],_NP.float64)):
            imag_part.append(_NP.float64(val))
          else:
            imag_part.append(_NP.float32(val))
      ans = list()
      for idx in range(len(real_part)):
        if isinstance(real_part[idx],_NP.float64):
          ct=_NP.complex128
        else:
          ct=_NP.complex64
        if idx < len(imag_part):
          ans.append(ct(complex(real_part[idx],imag_part[idx])))
        else:
          ans.append(ct(complex(real_part[idx])))
      if len(dargs[0].shape) == 0:
        ans=ans[0]
      else:
        ans=_NP.array(ans).reshape(dargs[0].shape)
      ans=_data.makeData(ans)
      units=UNITS_OF(args[0]).evaluate()
      if units.data().strip() != '':
        ans=ans.setUnits(units)
      if isinstance(args[0],_data.Signal):
        ans = _updateSignal(args[0],ans)
      return ans

class COMMA(_completed):
    """      CC Operation. 
      
      Evaluate arguments, keep only last. 
      
      Usual Form.       A,B,... . 
      Function Form.    COMMA(A,B,...). 
 
      Arguments May be any expressions. Note that used as an argument of 
                a function, it must be parenthesized. 
 
      Result..  That of the last argument. 
 
      Example.  _A=5,_B=6,_A+_B is 11 with variables _A and _B set."""
    min_args=2
    max_args=254
    name='COMMA'
    opcode=98
    def _evaluate(self):
      args=self.evaluateArgs()
      return args[-1]

_compile=_mimport('compile',1)
COMPILE=_compile.COMPILE

class COMPLETION_MESSAGE_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the completion field. 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_ACTION, the completion_message field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='COMPLETION_MESSAGE_OF'
    partnames=('completionMessage',)
    opcode=442

class COMPLETION_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the completion field. 
 
      Argument. Descriptor as below. 
 
      Result..  DISPATCH_OF(A) is searched for this: 
                DSC$K_DTYPE_DISPATCH, the completion field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='COMPLETION_OF'
    opcode=100

class CONCAT(_completed):
    """      Character Elemental. 
      
      Concatenate text. 
      
      Usual Form        STRING_A // STRING_B ... . 
      Function Form     CONCAT(STRING_A,STRING_B,...). 
 
      Arguments Must be character. Limit 253 character expressions. 
 
      Signals.  The single signal or the smallest. 
      Units...  The single or matching units, else bad. 
      Form....  Character of compatible shape with lengths summed. 
 
      Result..  The element-by-element concatenation of text elements 
                STRING_A, STRING_B, ... . 
                Note: compiled adjacent text strings are concatenated. 
                Immediate at compilation. 
 
      Example.  "ABC" // 'DEF' is "ABCDEF" """
    min_args=2
    max_args=254
    name='CONCAT'
    opcode=101
    def _evaluate(self):
      args=self.evaluateArgs()
      dargs=_dataArgs(args)
      ans=''
      for i in dargs:
        ans+=str(i)
      ans=_data.makeData(ans)
      units=UNITS_OF(args[0]).evaluate()
      if units.data().strip() != '':
        ans=ans.setUnits(units)
      if isinstance(args[0],_data.Signal):
        ans = _updateSignal(args[0],ans)
      return ans

class CONDITIONAL(_completed):
    """      CC-style Elemental.
      
      Select from 2 sources according to a mask. 
      
      Usual Form        MASK ? TSOURCE : FSOURCE. 
      Function Form     CONDITIONAL(TSOURCE,FSOURCE,MASK). 
 
      >>>>>>>>>WARNING, range and conditional nesting may be confusing, 
                use parentheses to help. For example, 2?3:4:5 will not 
                compile but 2?3:(4:5) or 2?(3:4):5 are fine. 
      Arguments 
        TSOURCE any type and shape. 
        FSOURCE any type and shape. 
        MASK    scalar logical, vector is treated as MERGE. 
 
      Signals.  That of the selected source. 
      Units...  That of the selected source. 
      Form....  That of the selected source. 
 
      Result..  MASK is examined and if a scalar true the source is 
                TSOURCE and if a scalar false the source is FSOURCE. 
      See also. MERGE, for a vector selection."""
    min_args=3
    max_args=3
    name='CONDITIONAL'
    opcode=102
    def _evaluate(self):
      args=self.evaluateArgs()
      try:
        if _data.Uint8(args[2]) == _data.Uint8(1):
          return self.args[0]
        else:
          return self.args[1]
      except:
        return self.args[1]

class CONDITION_OF(_PART_OF):
    """      MDS Operation.
      
      Get the condition field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_CONDITION, the condition field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='CONDITION_OF'
    opcode=401

class CONJG(_completed):
    """      F90 Numeric Elemental.
      
      Conjugate of a complex number. 
 
      Argument. Z must be complex. 
 
      Signals.  Same as Z. 
      Units...  Same as Z. 
      Form....  Same as Z. 
 
      Result..  If Z is CMPLX(x,y), the result is CMPLX(x,-y). Integers 
                and reals are not converted. 
 
      Example.  CONJG(CMPLX(2.0,3.0)) is CMPLX(2.0,-3.0)."""
    min_args=1
    max_args=1
    name='CONJG'
    opcode=103
    def _evaluate(self):
      args=self.evaluateArgs()
      if isinstance(args[0],(_data.Complex64,_data.Complex128)):
        ans=_data.makeData(args[0].value.conjugate())
      units=UNITS_OF(args[0]).evaluate()
      if units.data().strip() != '':
        ans=ans.setUnits(units)
      if isinstance(args[0],_data.Signal):
        ans = _updateSignal(args[0],ans)
      return ans

class CONTINUE(_toBeCompleted):
    """      CC Statement.
      
      Take next iteration of FOR or WHILE loop. 
      
      Usual Form        CONTINUE;. 
      Function Form     CONTINUE(). May be syntatically invalid. 
 
      Arguments None. 
 
      Results.  None. 
 
      Example.  FOR (_J=SIZE(_X); --_J>=0; ) { 
                        IF (_X[_J]) CONTINUE; 
                        ... 
                } 
                where lots of code is skipped for those true."""
    min_args=0
    max_args=0
    name='CONTINUE'
    syntax="CONTINUE"
    opcode=104

class COS(_completed):
    """      F90 Mathematical Elemental.
      
      Cosine of angle in radians. 
 
      Argument. X (radians) must be real or complex. HC is converted to GC. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
      Result..  Processor approximation to cos(X). Real X and real part 
                of complex X is in radians. 
 
      Example.  COS(1.0) is 0.54030231, approximately."""
    min_args=1
    max_args=1
    name='COS'
    opcode=106
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.cos(args[0].value))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],COS(args[0].value)._evaluate())
        else:
            raise _data.TdiException("Invalid argument type for COS function: %s" % (str(type(args[0])),))
        return ans

class COSD(_completed):
    """      Mathematical Elemental.
      
      Cosine of angle in degrees. 
 
      Argument. X (degrees) must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to cos(X) with X in degrees. 
 
      Example.  COSD(60.0) is 0.5, approximately."""
    min_args=1
    max_args=1
    name='COSD'
    opcode=107
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.cos(args[0].value/360.*2*_NP.pi))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],COSD(args[0].value)._evaluate())
        else:
            raise _data.TdiException("Invalid argument type for COSD function: %s" % (str(type(args[0])),))
        return ans

class COSH(_completed):
    """      F90 Mathematical Elemental. 
      
      Hyperbolic cosine. 
 
      Argument. X must be real. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to cosh(X). 
 
      Example.  COSH(1.0) is 1.5430806, approximately."""
    min_args=1
    max_args=1
    name='COSH'
    opcode=108
    def _evaluate(self):
      args=self.evaluateArgs()
      if isinstance(args[0],_data.Scalar):
        ans = type(args[0])((pow(_NP.e,args[0].value)+pow(_NP.e,-1.*args[0].value))/2.)
      elif isinstance(args[0],_data.Signal):
        ans = _updateSignal(args[0],COSH(args[0])._evaluate())
      else:
        raise _data.TdiException("Invalid argument type for COSD function: %s" % (str(type(args[0])),))
      return ans

class COUNT(_completed):
    """      F90 Transformation. 
      
      Count the number of true elements in MASK along 
                dimension DIM. 
 
      Arguments Optional: DIM. 
        MASK    logical array. 
        DIM     integer scalar from 0 to n-1, where n is rank of MASK. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer. It is scalar if DIM is absent or MASK is a 
                vector; otherwise, the result is an array of rank n-1 
                and of shape like MASK's with DIM subscript omitted. 
 
      Result. 
        (i)     COUNT(MASK) is equal to the number of true elements of 
                MASK and is 0 if no element of MASK is true or MASK is 
                size zero. 
        (ii)    For a vector MASK, COUNT(MASK,DIM) is equal to 
                COUNT(MASK). For higher dimensional cases, the value of 
                an element of the result is COUNT of elements of MASK 
                varying the DIM subscript. 
 
      Examples. 
        (i)     COUNT([$TRUE,$FALSE,$TRUE]) is 2. 
        (ii)    COUNT((_B=[[1,3,5],[2,4,6]]) NE (_c=[[0,3,5],[7,4,8]])) 
	             is 3. 
                                 
                COUNT(_B NE _c,1) is [2, 0, 1]."""
    min_args=1
    max_args=2
    name='COUNT'
    opcode=109
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        if len(dargs) == 1:
          return _data.Uint8((dargs[0]&1).sum())
        else:
          dim=int(args[1])
          return _data.Uint8((dargs[0]&1).transpose().sum(dim)) ##### Transpose to match tdishr

class CULL(_toBeCompleted):
    """      MDS Operation. 
      
      Removes values not in bounds. 
      
      Arguments Optional: DIM and X. 
        A       MDS signal or dimension or VMS array. 
        DIM     scalar integer from 0 to rank of A less one. 
                Must be 0 or absent for a signal. 
        X       non-complex scalar or array of numbers to check 
                if bounded. 
 
      Signals.  Same as X. 
      Units...  Same as specified dimension if a signal or dimension. 
      Form....  Shape of X and type from specified dimension. 
 
      Result..  X values that are out of range are eliminated. 
        (i)     If A is an array, the bounds of the array are used. 
        (ii)    If A is a dimension or the specified dimension of a 
                signal, the extreme data value of the axis are used. 
 
      Examples. 
        (i)     CULL(1..5,,0..7) is [1,2,3,4,5]. 
        (ii)    CULL(BUILD_DIM(BUILD_WINDOW(2,5,1.1),BUILD_RANGE(,,3)), 
                0,5..8) is [8] because the limits are 7.1 and 16.1. 
 
      See also. EXTEND to replace bad values with the limits."""
    min_args=1
    max_args=4
    name='CULL'
    opcode=390

class CVT(_completed):
    """      Conversion Elemental. 
      
      Convert data type by example. 
 
      Arguments 
        A       any type that can be converted to MOLD type. 
        MOLD    any type that A can be converted from. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Shape of A and type of MOLD. 
 
      Result..  The converted value of the corresponding element of A. 
                Types permitted are byte, word, long, quadword, and 
                octaword unsigned and signed; F, D, G, and H floating 
                real and complex; text. (No text to numbers, today.) 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  CVT(123,"1234") is " 123", four character of long. 
                Note, the default string would have been 12 characters."""
    min_args=2
    max_args=2
    name='CVT'
    opcode=111
    def _evaluate(self):
      args=self.evaluateArgs()
      dargs=_dataArgs(args)
      if isinstance(dargs[1],_NP.ndarray):
        t=type(dargs[1].flat[0])
      else:
        t=type(dargs[1])
      ans=self.makeData(t(dargs[0]))
      units=UNITS_OF(args[0]).evaluate()
      if units.data().strip() != '':
        ans=ans.setUnits(units)
      if isinstance(args[0],_data.Signal):
        ans = _updateSignal(args[0],ans)
      return ans


class DATA(_completed):
    """      MDS Operation.
      
      Removes signal and parameter descriptors and evaluates 
                ranges and tries to give a VMS data type. 
 
      Argument. X may be any data type with a data/value field. 
 
      Signals.  None. 
      Units...  None unless X is AS_IS. 
      Form....  VMS scalar or array. 
 
      Result..  For a dimension, the axis values. 
                For a signal or with_units, the evaluated data field. 
                For a param, the evaluated value field. 
                For a range, the values. 
                For VMS data, no change is made. 
                Immediate at compilation. 
 
      Example.  DATA(BUILD_SIGNAL(42.*$VALUE,6)) is 252."""
    min_args=1
    max_args=1
    name='DATA'
    opcode=112
    def _evaluate(self):
      args=self.evaluateArgs()
      if isinstance(args[0],_data.Scalar):
        return args[0]
      elif isinstance(args[0],(_data.Signal,)):
        dVALUE._push(args[0].raw)
        try:
          ans=DATA(args[0].value)._evaluate()
        finally:
          dVALUE._pop()
        return ans
      elif isinstance(args[0],(_data.Param,)):
        return DATA(args[0].value)._evaluate()
      elif isinstance(args[0],(_data.Range,_data.Dimension)):
        try:
          old=self.usePython
          self.usePython=False
          ans = DATA(args[0]).evaluate() ############ Need to implement range and dimension evaluators
        finally:
          self.usePython=old
        return ans
      elif isinstance(args[0],_data.EmptyData):
	return _data.EmptyData()
      else:
        raise _data.TdiException('Cannot get data from %s' % (str(type(args[0])),))

class DATA_WITH_UNITS(_completed):
    """      MDS Operation.
      
      Removes signal and parameter descriptors and evaluates 
                ranges and tries to give a VMS data type bound in a 
                with_units descriptor. 
 
      Argument. X may be any data type with a data/value field. 
 
      Signals.  None. 
      Units...  Same as X. 
      Form....  With_units descriptor with a VMS scalar or array data 
                field. The units pointer may be null or point to a 
                standard units data (today, text). 
 
      Result..  For a dimension, the axis values. 
                For a signal or with_units, the evaluated data field. 
                For a param, the evaluated value field. 
                For a range, the values. 
                For VMS data, no change is made. 
                The result has a data field and if there are units the 
                units descriptor with the first units found. 
                Immediate at compilation. 
 
      Example.  DATA_WITH_UNITS(BUILD_SIGNAL(42.*$VALUE, 
                BUILD_WITH_UNITS(6,'count'//'s')) is 
                Build_With_Units(252,'counts')."""
    min_args=1
    max_args=1
    name='DATA_WITH_UNITS'
    opcode=404
    def _evaluate(self):
      args=self.evaluateArgs()
      dargs=_dataArgs(args)
      return _data.makeData(dargs[0]).setUnits(args[0].units)

class DATE_TIME(_completed):
    """      VMS IO.
      
      The current/specified data and time as a text string. 
 
      Arguments Optional TIME must be a quadword (64-bit) positive 
                absolute time or negative delta time. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Character scalar of length 23. 
 
      Result..  The current date and time. 
 
      Example.  DATE_TIME() might be 26-JAN-1990 15:15:19.54."""
    min_args=0
    max_args=1
    name='DATE_TIME'
    opcode=114
    def _evaluate(self):
      if len(self.args)==0:
        return _data.QuadToDate(_data.DateToQuad('now'))
      else:
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        return _data.QuadToDate(int(dargs[0]))

class DBLE(_completed):
    """      F90 Modified Conversion Elemental.
      
      Double the precision of a number. 
 
      Argument. A must be numeric and must not be octaword or H floating 
                because they are maximum precision. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Twice the precision of the argument. Byte becomes word, 
                word becomes long, long becomes quadword, quadword 
                becomes octaword, F floating becomes D, D or G floating 
                becomes H. Unsigned, signed, real, and complex types 
                remain so. 
      >>>>>>WARNING F90 always converts to a double-precision real--D_FLOAT. 
 
      Examples. DBLE(3) is 3Q. DBLE(3.0) is 3D0."""
    min_args=1
    max_args=1
    name='DBLE'
    opcode=115
    def _evaluate(self):
      cvtTable={_NP.uint8:_NP.uint16, _NP.uint16:_NP.uint32, _NP.uint32:_NP.uint64,
                _NP.int8: _NP.int16,  _NP.int16: _NP.int32,  _NP.int32:_NP.int64,
                _NP.float32:_NP.float64,_NP.complex64:_NP.complex128}
      args=self.evaluateArgs()
      dargs=_dataArgs(args)
      if isinstance(dargs[0],_NP.ndarray):
        t=type(dargs[0].flat[0])
      else:
        t=type(dargs[0])
      if t in cvtTable:
        ans=self.makeData(cvtTable[t](dargs[0]))
      else:
        raise _data.TdiException("Cannot double size of type %s" % str(type(self.makeData(dargs[0]))))
      units=UNITS_OF(args[0]).evaluate()
      if units.data().strip() != '':
        ans=ans.setUnits(units)
      if isinstance(args[0],_data.Signal):
        ans = _updateSignal(args[0],ans)
      return ans

class DEALLOCATE(_toBeCompleted):
    """      Variables.
      
      Release variables by wildcarded name or release all 
                private variables. 
 
      Arguments Optional: STRING.... 
        STRING,... character scalars. Wildcards % and * are allowed. 
                If STRING is absent, all private variables are released. 
      Result..  None. 
 
      Side Effect. The variable is no longer allocated. 
 
      Example.  DEALLOCATE("_A*") removes all starting with _A."""
    min_args=0
    max_args=254
    name='DEALLOCATE'
    opcode=116

class DEBUG(_toBeCompleted):
    """      Compile Operation.
      
      Controls debugging output. 
 
      Argument. OPTION is integer scalar. 
                OPTION = 1, "prepends" the first error message text. 
                OPTION = 2, prints the error message. 
                OPTION = 4, clears the error message and status. 
                OPTION is the bitwise combination of these codes. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Character string scalar. 
 
      Result..  Previous value of debugging messages. 
                An empty string is returned if no error was detected. 
 
      Example.  DEBUG(7) appends the first detected error's text, 
                prints the message, and frees the message string. 
                DEBUG(5) can fetch and clear the error string."""
    min_args=0
    max_args=1
    name='DEBUG'
    opcode=117

class DECOMPILE(_toBeCompleted):
    """      Compile Operation.
      
      Converts the argument expression to text that will 
                compile to the same expression. 
 
      Arguments Optional: MAX. 
        X       any MDS or VMS data description. 
        MAX     Integer scalar for the maximum number of vector elements 
                to display. Default is all. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Character scalar. Length limit is 65535. 
 
      Result..  The text, less comments, that could make the argument. 
 
      Example.  DECOMPILE('_A+\TOP.XRAY.CHAN01:DATA/*my expression*/') 
                is _A + \TOP.XRAY.CHAN01:DATA. Some forms are converted 
                to the most common one: 'CONCAT(_B,"X")' will be 
                _B // "X". Control characters, double quotes, and 
                backslashes (\) are converted to their backslash form."""
    min_args=1
    max_args=2
    name='DECOMPILE'
    opcode=119

class DECOMPRESS(_toBeCompleted):
    """      Miscellaneous.
      
      Expand compressed data into original form. 
 
      Arguments Optional: IMAGE, ROUTINE. 
        IMAGE   character scalar of SYS$SHARE:.EXE file or logical name. 
                Default is MDSSHR if no ROUTINE. 
        ROUTINE character scalar of entry point name in shared image. 
                Default is MDS$DECOMPRESS 
        SHAPE   Expanded form data shape. 
        DATA    A vector of any type that has the compressed data. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Original form, usually. 
 
      Result..  The original data. This is done automatically when 
                compressed, CLASS_CA, data is fetched from the tree. 
 
      Example.  DECOMPRESS(,,BUILD_ARRAY(10), 
                [0x00880246, 0x84620800LU, 0x4befcb4e, 0x080a]) 
                gives [0,164,228,252,256,250,238,224,207,190]. 
                (Actually this does not save enough space so the 
                compression would not take place.)"""
    min_args=4
    max_args=4
    name='DECOMPRESS'
    opcode=120

class DEFAULT(_toBeCompleted):
    """      CC Statement. 
      
      Required Usual Form. CASE DEFAULT STMT. 
      Function Form     DEFAULT(STMT,...). May be syntatically invalid. 
      Argument. STMT must be a statement, simple or compound 
                (like {S1 S2}) or multiple (like S1 S2). 
      >>>>>>WARNING, only one CASE DEFAULT should appear in a SWITCH. 
 
      Result..  None. 
 
      Example.  SWITCH (_k) { 
                CASE (1) _j=_THING1; BREAK; 
                CASE (4.5:5.5) _j=_OTHER_THING; BREAK; 
                CASE DEFAULT ABORT(); 
                }."""
    min_args=1
    max_args=254
    name='DEFAULT'
    syntax='DEFAULT'
    opcode=121

class DESCR(_toBeCompleted):
    """            CALL mode. 

	    Pass the data of the argument by descriptor.

            Argument.   X is any type, scalar or array that DATA can evaluate.

            Use.....    Descriptor of VMS data, like Fortran %DESCR(1.23).
                        The descriptor of the DATA of the argument. For X alone,
                        non-data forms may be passed. Many programs cannot handle
                        these forms."""
    min_args=1
    max_args=1
    name='DESCR'
    opcode=123

class DIAGONAL(_completed):
    """      Transformation.
      
      Create a diagonal matrix from its diagonal. 
 
      Arguments Optional: FILL. 
        ARRAY   numeric or character vector. 
        FILL    scalar converted to type of ARRAY. Default is numeric 0 
                or character blanks. 
 
      Signals.  Same as ARRAY. 
      Units...  Same as ARRAY. 
      Form....  Rank-two of shape [n,n], where n is the size of ARRAY. 
 
      Result..  Element [j,j] is ARRAY[j], for j from 0 to n-1. 
                All other elements are FILL. 
 
      Example.  DIAGONAL([1,2,3]) is [1 0 0]. 
                                     [0 2 0] 
                                     [0 0 3]"""
    min_args=1
    max_args=2
    name='DIAGONAL'
    opcode=124
    def _evaluate(self):
      args=self.evaluateArgs()
      dargs=_dataArgs(args)
      if isinstance(dargs[0],_NP.ndarray):
        if len(dargs[0].shape)==1:
          ans=_NP.ndarray(shape=[dargs[0].shape[0],dargs[0].shape[0]],dtype=dargs[0].dtype)
          if len(dargs) > 1:
            ans.fill(dargs[1])
          else:
            if issubclass(dargs[0].dtype.type,_NP.number):
              ans.fill(0)
            else:
              ans.fill('')
          for idx in range(dargs[0].shape[0]):
            ans[idx][idx]=dargs[0][idx]
          ans=_data.makeData(ans)
          units=UNITS_OF(args[0]).evaluate()
          if units.data().strip() != '':
            ans=ans.setUnits(units)
          if isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],ans)
          return ans
        else:
          raise _data.TdiException('Diagonal requires a 1-D array for first argument')
      else:
        raise _data.TdiException('Diagonal requires a 1-D array for first argument')

class DIGITS(_toBeCompleted):
    """      F90 Inquiry. 
      
      The number of significant digits in the model representing 
                the same type as the argument. 
 
      Argument. X must be numeric. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
      Result..  The number of non-sign bits in an integer or the number 
                of fraction bits in a real or complex number. 
 
      Example.  DIGITS(1.0) is 24 on the VAX."""
    min_args=1
    max_args=1
    name='DIGITS'
    opcode=125
    digits={2:8,3:16,4:32,5:64,6:7,7:15,8:31,9:63,10:24,11:56,12:53,
            13:56,27:53,29:53,52:24,53:53,54:24,55:53}
    def _evaluate(self):
      arg=DATA(self.args[0]).evaluate()
      if arg.dtype_mds in self.digits:
        return _data.Int32(self.digits[arg.dtype_mds])
      else:
        raise _data.TdiException('Cannot get digits of type %s' % (str(type(arg)),))

class DIM(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      The difference X-Y if it is positive; otherwise, 
                zero. 
 
      Arguments X and Y must be integer or real. 
                Complex numbers are an error. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Compatible form of X and Y. F90 says type of X. 
 
      Result..  X-Y if X>Y and zero otherwise. 
 
      Example.  DIM(-3.0,2.0) is 0.0."""
    min_args=2
    max_args=2
    name='DIM'
    opcode=126

class DIM_OF(_toBeCompleted):
    """      MDS/VMS Operation. 
      
      Get the dimension. 
 
      Arguments Optional: N. 
        A       VMS or MDS descriptor as below. 
        N       integer scalar from 0 to the number of dimension of a 
                signal. 
 
      Result..  A is searched for these: 
                DSC$K_CLASS_A, range of N-th lower and upper bounds. 
                DSC$K_CLASS_APD, range of N-th lower and upper bounds. 
                DSC$K_CLASS_CA, range of N-th lower and upper bounds. 
                DSC$K_DTYPE_DIMENSION, unchanged. 
                DSC$K_DTYPE_SIGNAL, the N-th dimension field. 
                Otherwise, an error. 
 
      Example.  DIM_OF([1,2,3]) is 0..2, the range from 0 to 2."""
    min_args=1
    max_args=2
    name='DIM_OF'
    opcode=127

class DISPATCH_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the dispatch field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_ACTION, the dispatch field. 
                DSC$K_DTYPE_DISPATCH, unchanged. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='DISPATCH_OF'
    opcode=128

class DIVIDE(_toBeCompleted):
    """      Numeric Elemental. 
      
      The quotient of two numbers. 
      
      Usual Form        X / Y. 
      Function Form     DIVIDE(X,Y). 
 
      Arguments X and Y must be numeric. 
 
      Signals.  Single signal or smaller data. 
      Units...  X units with inverted Y units separated by a slash. 
      Form....  The compatible form of X and Y. 
 
      Result..  The quotient without remainder of X/Y. If the result is 
                real or complex there may be rounding. Integer division 
                truncates. Complex division is 
                CMPLX((RX*RY-IX*IY)/DEN,(RY*IX-RX*IY)/DEN) with 
                DEN=RY^2+RI^2, where RX=REAL(X), IX=AIMAG(X), etc. The 
                exponents are scaled to prevent overflow or underflow. 
      >>>>>>>>>WARNING, integer divide by zero is ignored. 
 
      Examples. 5/3 is 1. 
                5/BUILD_WITH_UNITS(3,"s") is BUILD_UNITS(1,"/s")."""
    min_args=2
    max_args=2
    name='DIVIDE'
    opcode=129

class DO(_toBeCompleted):
    """      CC Modified Statement. 
      
      Repeat until expression is false. 
      
      Required Usual Form. DO {STMT} WHILE (X);. 
      Function Form     DO(TEST,STMT...). May be syntatically invalid. 
 
      Arguments 
        STMT    statement list. The curly braces are required! 
        TEST    logical scalar. 
      >>>>>>Note that TEST is first argument of call form. 
      >>>>>>WARNING, multiple statements in call form are considered 
                to be in braces. 
 
      Result..  None. 
 
      Example.  DO { 
                        _J=_X[_J]; 
                } WHILE (_J);."""
    min_args=2
    max_args=254
    name='DO'
    opcode=131

class DOT_PRODUCT(_toBeCompleted):
    """      F90 Transformation. 
      
      Performs dot-product multiplication of numeric. 
                ((Non-F90, treats logicals as integers.)) 
 
      Arguments VECTOR_A and VECTOR_B must be numeric vectors. 
 
      Signals.  None. 
      Units...  Single or common units, else bad. 
      Form....  Compatible scalar. 
 
      Result..  For integer or real, result is SUM(VECTOR_A*VECTOR_B); 
                for complex, SUM(CONJG(VECTOR_A),VECTOR_B). 
                For zero elements the result is zero. 
 
      Example.  DOT_PRODUCT([1,2,3],[2,3,4]) is 20."""
    min_args=2
    max_args=2
    name='DOT_PRODUCT'
    opcode=132

class DO_TASK(_toBeCompleted):
    """      Execute Task

     Executes the task item found in the argument.

     ARGUMENT TASK refers to an ACTION or a TASK"""
    min_args=1
    max_args=1
    name='DO_TASK'
    opcode=448

class DPROD(_toBeCompleted):
    """      F90 Modified Numeric Elemental. 
      
      Double precision product. 
 
      Arguments X and Y must be numeric except octaword or H floating. 
                For F90, they must be default real and result is double. 
 
      Signals.  Single signal or smaller data. 
      Units...  Same as for X * Y. 
      Form....  Twice the precision of the compatible form. 
 
      Result..  The product of X and Y with each converted to twice 
                their precision. 
 
      Examples. DPROD(3,4) is 12Q. DPROD(-3.0,2.0) is -6.0D0."""
    min_args=2
    max_args=2
    name='DPROD'
    opcode=133

class DSCPTR(_toBeCompleted):
    """      MDS Operation. 
      
      Get a field of any class-R descriptor. 
 
      Arguments Optional: N. 
        A       any class-R or class-APD descriptor. 
        N       integer scalar from 0 to the number of pointers less 1. 
 
      Result..  The N-th descriptor of A for class R or the N-th list 
                element for class APD. 
                Descriptor data types (DSC$K_DTYPE_DSC) are removed. 
                Immediate at compilation for non-class-R. 
                Use DSCPTR for A without NID, PATH, or variable. 
                Use DSCPTR_OF for A including them. 
      >>>>>>>>>WARNING, the N-th element may not describe the N-th data value. 
 
      Example.  DSCPTRS(A+B,1) is B. 
 
      See also. ARG_OF for argument fields of some class-R descriptors 
                and specific xxx_OF routines for other fields."""
    min_args=1
    max_args=2
    name='DSCPTR'
    opcode=134

class DSCPTR_OF(_toBeCompleted):
    """      MDS Operation. 
      
      Get a field of any class-R descriptor. 
 
      Arguments Optional: N. 
        A       any class-R or class-APD descriptor. 
        N       integer scalar from 0 to the number of pointers less 1. 
 
      Result..  The N-th descriptor of A for class R or the N-th list 
                element for class APD. 
                Descriptor data types (DSC$K_DTYPE_DSC) are removed. 
                Immediate at compilation for non-class-R. 
                Use DSCPTR for A without NID, PATH, or variable. 
                Use DSCPTR_OF for A including them. 
      >>>>>>>>>WARNING, the N-th element may not describe the N-th data value. 
 
      Example.  DSCPTR_OF(A+B,1) is B. 
 
      See also. ARG_OF for argument"""
    min_args=1
    max_args=2
    name='DSCPTR_OF'
    opcode=436

class DSQL(_toBeCompleted):
    """       Execute a MSsql query

    _num=DSQL(sqlcommand,arg0,arg1,...,retarg0,retarg1,...)

    Eample.
          set_database('logbook')
          _rows=dsql('select count(*) from entries',_num)"""
    min_args=1
    max_args=254
    name='DSQL'
    opcode=415

class DTYPE_RANGE(_toBeCompleted):
    """Compile time evaluation of a BUILD_RANGE

    Form:         DTYPE_RANGE(START,END,INCREMENT)

    ARGUMENTS:    OPTIONAL INCREMENT
                  START  anything that evaluates to a numeric value to denote
                         start of range
                  END    anything that evaluates to a numeric value to denote
                         end of range
                  INCRMENT anything that evaluates to a numeric valu to denote
                         increment from one to the next

    Example:     DTYPE_RANGE(1,100,10) is
                 [1,11,21,31,41,51,61,71,81,91]
                 Equivalent to `DATA(1 : 100 : 10)"""
    min_args=2
    max_args=3
    name='DTYPE_RANGE'
    opcode=292

class D_COMPLEX(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to D-precision floating Complex. 
 
      Argument. A must be numeric. 
  
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  D-precision complex. 
 
      Result..  If Y is absent and X is complex, the AIMAG(X) is used 
                for Y. If X and Y are present, the real parts of each 
                are used. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  D_COMPLEX(3,4.1) is CMPLX(3.0D0,4.1D0), approximately."""
    min_args=1
    max_args=2
    name='D_COMPLEX'
    opcode=139

class D_FLOAT(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to D-precision floating real. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  D-precision real. 
 
      Result..  Integers, reals and the real part of complex numbers are 
                converted to D-precision reals. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  D_FLOAT(12), D_FLOAT(12.) D_FLOAT(12H0) are 12D0, 
                approximately."""
    min_args=1
    max_args=1
    name='D_FLOAT'
    opcode=140

class ELBOUND(_toBeCompleted):
    """      Inquiry.  All the lower bounds of an array or signal or a specified 
                lower bound. 
 
      Arguments Optional: DIM. 
        ARRAY   any type array or signal. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
 
      Signals.  None. 
      Units...  None if array, those of combined dimensions if signal. 
      Form....  Scalar if DIM present, otherwise, vector of size n. 
                Integer for an array; combined type of dimensions for a 
                signal. 
 
      Result..  ELBOUND(ARRAY,DIM) is equal to the lower bound 
                for subscript DIM of ARRAY. If no bounds were effective 
                it is 0. ELBOUND(ARRAY) is whose j-th component is equal 
                to ELBOUND(ARRAY,j) for each j, 0 to n-1. 
                For a signal, the lower bound on the dimension if it is 
                of DTYPE_DIMENSION, else as for an array. 
 
      Examples. ELBOUND(_A=SET_RANGE(2:3,7:10,0)) is [2,7] and 
                ELBOUND(_A,1) is 7. 
 
      See also  UBOUND for upper bound, SHAPE for number of elements, 
                SIZE for total elements, and E... for signals."""
    min_args=1
    max_args=2
    name='ELBOUND'
    opcode=143

class ELEMENT(_toBeCompleted):
    """      DCL Character Elemental. 
      
      Extracts an element from a string in which the 
                elements are separated by a delimiter character. 
 
      Arguments 
        NUMBER  integer. First item is NUMBER=0. 
        DELIMITER character, length one. 
        STRING  character. 
 
      Signals.  Same as STRING. 
      Units...  Same as STRING. 
      Form....  Character of same length as STRING. Compatible shape. 
      >>>>>>>>>WARNING, the DCL function trims the result, not so here. 
                It may be trimmed, someday for scalars only. 
 
      Result..  The string from the NUMBER-th instance of the delimiter 
                to the next instance or the end of string. NUMBER=0 gets 
                the part of the string up to the first delimiter. 
                A blank string is returned if NUMBER-th not found. 
 
      Examples. ELEMENT(1,'/','A/B/C') is "B    ". 
                ELEMENT(4,'/','12') is "  "."""
    min_args=3
    max_args=3
    name='ELEMENT'
    opcode=374

class ELSE(_toBeCompleted):
    """      CC-style Operation. Alternative to IF. """
    min_args=0
    max_args=0
    name='ELSE'
    opcode=144
    syntax='ELSE'

class END_OF(_toBeCompleted):
    """      MDS Operation. 
      
      Get the end field. 
 
      Arguments Optional: N. 
        A       Descriptor as below. 
        N       integer scalar, for slopes from 0 to the number of 
                segments less two. The last segment has no end if the 
                axis is infinite. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_RANGE, the end field. 
                DSC$K_DTYPE_SLOPE, N-th segment's end field. !deprecated! 
                DSC$K_DTYPE_WINDOW, the endidx field. 
                Otherwise, an error. 
 
      Example.  END_OF(1..10) is 10. """
    min_args=1
    max_args=2
    name='END_OF'
    opcode=148

class EPSILON(_toBeCompleted):
    """      F90 Inquiry. 
      
      A positive model number that is almost negligible compared 
                to unity in the model representing numbers of the same 
                type as the argument. 
 
      Argument. X must be real or complex, scalar or array. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Scalar of same type as real part of X. 
 
      Result..  The result is b^(1-p), where b is the digit base and p 
                is the number of digits in model numbers like X. 
 
      Example.  EPSILON(1.0) is 2^-23 on the VAX."""
    min_args=1
    max_args=1
    name='EPSILON'
    opcode=150

class EQ(_toBeCompleted):
    """      Logical Elemental. 
      
      Tests for equality of two values. 
      
      Usual Forms       X == Y, X NE Y. 
      Function Form     EQ(X,Y). 
 
      Arguments X and Y must both be numeric or character. 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of same shape. 
 
      Result..  True if X and Y are the equal; otherwise, false. 
                $ROPRAND is not equal to any value. 
      >>>>>>>>>WARNING, floating point operations may not match an exact 
                calculation for nonterminating binary fractions. You 
                cannot predict that .1+.1==.2 is true. Integer values 
                may be truncated when matched to floating numbers. 
 
      Example.  2==2.0 is $TRUE."""
    min_args=2
    max_args=2
    name='EQ'
    opcode=151
    syntax='arg1 == arg2'

class EQUALS(_toBeCompleted):
    """      Variable Operation. 
      
      Store in a name variable. 
      
      Usual Form        NAME = X. 
      Function Form     EQUALS(NAME,X). 
 
      Arguments 
        NAME    variable name optionally preceded by PRIVATE or PUBLIC. 
                Begin name with underscore (_) for user variables. 
                Dollar sign ($) is used for system variables. A text 
                string but not an expression is acceptable. 
        X       an expression of any type. 
 
      Result..  Same as X. 
 
      Side Effect. NAME now has value X. 
 
      Example.  _A=[1,2,3]."""
    min_args=2
    max_args=2
    name='EQUALS'
    syntax="_x = value"
    opcode=152

class EQUALS_FIRST(_toBeCompleted):
    """      Variable Elemental. 
      
      Store in a name variable using variable in binary 
      operation. This saves writing the variable name twice. 
      
      Usual Forms      
                NAME^=Y, 
                NAME*=Y, NAME/ =Y, NAME MOD=Y, 
                NAME+=Y, NAME-=Y, 
                NAME<<=Y, NAME>>=Y, 
                NAME//=Y, NAME IS_IN=Y, 
                NAME>==Y, NAME GE=Y, NAME> =Y, NAME GT=Y, 
                NAME<==Y, NAME LE=Y, NAME< =Y, NAME LT=Y, 
                NAME===Y, NAME EQ=Y, NAME!==Y, NAME/==Y, 
                NAME<>=Y, NAME NE=Y, 
                NAME&=Y, NAME|=Y, NAME EQV=Y, NAME NEQV=Y, 
                NAME&&=Y, NAME AND=Y, NAME AND_NOT=Y, 
                NAME NAND=Y, NAME NAND_NOT=Y, 
                NAME||=Y, NAME OR=Y, NAME OR_NOT=Y, 
                NAME NOR=Y, NAME NOR_NOT=Y, 
                NAME@=Y. 
 
      Arguments 
        X       an expression with a binary (two-argument) operator. The 
                first argument must be a variable name, like in NAME+6. 
                Only those listed above are acceptable to the compiler. 
      >>>>>>>>>WARNING, special punctuation is required for /, >, and < 
          because they may be confused with single operators /=, >=, and <=. 
 
      Result..  Same as X. 
 
      Side Effect. NAME now has value X or X operated on by Y. 
 
      Example.  For _A=[1,2,3], _A+=4 is [5,6,7]."""
    min_args=1
    max_args=1
    name='EQUALS_FIRST'
    opcode=153
    syntax="_x (operator)= value"

class EQV(_toBeCompleted):
    """      Logical Elemental. 
      
      Test that logical values are equal. 
 
      Arguments L and M must be logical (lowest bit is 1 for true). 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if both are true or both are false; 
                otherwise, false. 
 
      Example.  2>3 EQV 3>4 is $TRUE."""
    min_args=2
    max_args=2
    name='EQV'
    opcode=154

class ERRORLOGS_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the errorlogs field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_ACTION, the errorlogs field. 
                Otherwise, an error. """
    min_args=1
    max_args=1
    name='ERRORLOGS_OF'
    opcode=398

class ERROR_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the error field of a build_with_error object. 
 
      Argument. Object with error field
 
      Result..  The value of the error field or an evaluation error"""
    min_args=1
    max_args=1
    name='ERROR_OF'
    opcode=446


class ESHAPE(_toBeCompleted):
    """      Inquiry.  
      
      The shape of an array or a scalar or a signal. 
 
      Arguments Optional: DIM (To follow F90, use ESIZE with a DIM). 
        SOURCE  any type scalar, array, or signal. 
        DIM     integer scalar from 0 to n-1, where n is rank of SOURCE. 
 
      Signals.  None. 
      Units...  None if array, that of combined dimensions of signal. 
      Form....  Scalar if DIM present; otherwise, vector of size n. 
                Integer for an array, combined type of dimensions for 
                a signal. 
 
      Result..  The shape of SOURCE for subscript DIM of SOURCE. 
                If no bounds were effective 
                it is one less than the multiplier for subscript DIM of 
                SOURCE. ESHAPE(ARRAY) has value whose j-th component is 
                equal to ESHAPE(ARRAY,j) for each j, 0 to n-1. 
                For a signal, the extent of the dimension if it is 
                of DTYPE_DIMENSION, else as for an array. This does not 
                include both bounds for integers. 
 
      Examples. ESHAPE(_A[2:5,-1:1]) is [4,3]. ESHAPE(3) is [], a 
                zero-length vector."""
    min_args=1
    max_args=2
    name='ESHAPE'
    opcode=155

class ESIZE(_toBeCompleted):
    """      Inquiry.  
      
      The extent an array or the total number of elements 
                in the array or signal. 
 
      Arguments Optional: DIM. 
        ARRAY   any type array or signal. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Scalar. Integer for array, 
                combined type of dimensions for signal. 
 
      Result..  Equal to the extent of dimension DIM of ARRAY 
                or, if DIM is absent, the total number of 
                elements of ARRAY. 
                For a signal, the extent of the dimension if it is 
                of DTYPE_DIMENSION, else as for an array. This does not 
                include both bounds for integers. The volume if no DIM. 
 
      Examples. ESIZE(_A[2:5,-1:1]),1) is 3. ESIZE(_A[2:5,-1:1]) is 12."""
    min_args=1
    max_args=2
    name='ESIZE'
    opcode=156

class EUBOUND(_toBeCompleted):
    """      Inquiry.  
      
      All the upper bounds of an array or signal or a specified 
                upper bound. 
 
      Arguments Optional: DIM. 
        ARRAY   any type array or signal. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
 
      Signals.  None. 
      Units...  None if array, that of combined dimensions of signal. 
      Form....  Scalar if DIM present; otherwise, vector of size n. 
                Integer for an array, combined type of dimensions for 
                a signal. 
 
      Result..  EUBOUND(ARRAY,DIM) is equal to the upper bound 
                for subscript DIM of ARRAY. If no bounds were effective 
                it is one less than the multiplier for subscript DIM of 
                ARRAY. EUBOUND(ARRAY) has value whose j-th component is 
                equal to EUBOUND(ARRAY,j) for each j, 0 to n-1. 
                For a signal, the upper bound on the dimension if it is 
                of DTYPE_DIMENSION, else as for an array."""
    min_args=1
    max_args=2
    name='EUBOUND'
    opcode=157

class EVALUATE(_toBeCompleted):
    """      Compile Operation. 
      
      Remove descriptors and node (NID and PATH) pointers 
                and evaluate functions. 
      
      Common Usual Form. `expression or `statement for compile-time evaluation. 
      >>>>>>>>>WARNING, because of its low precedence, parentheses must be 
                outside the ` to constrain it unlike the other operators. 
 
      Argument. X is any MDS or VMS data description. VMS and most MDS 
                data types are passed. A NID or PATH is found in the 
                current tree and re-evaluated. FUNCTION data types are 
                executed and their result returned but not re-evaluated. 
 
      Signals.  None. 
      Units...  None. 
      Form....  A data descriptor. 
 
      Result..  Depends on the expression to be evaluated. 
 
      Examples. EVALUATE(2+3) is 5. 
                (`2+3)+4 compiles to 5+4, which will evaluate to 9."""
    min_args=1
    max_args=1
    name='EVALUATE'
    opcode=158

class EXECUTE(_completed):
    """      Compile Operation. 
      
      Convert a text string into a functional form of the 
                expression with the possibility of including other 
                descriptors. Comments (/* ... */) are removed and may be 
                nested. Then EVALUATE the expression. 
 
      Arguments Optional: ARG,... . 
        STRING  character scalar. 
        ARG,... other expressions that may be accessed as $k where k 
                runs from 1 to the number of additional arguments. 
                Successive arguments may be accessed by $ starting from 
                the first. Once $k appears, subsequent $'s designates 
                the arguments following it. The $k allows inputs to be 
                used several times but k must be less than the number of 
                arguments actual passed, maximum 253. $0 is STRING. 
 
      Signals.  None. 
      Units...  None. 
      Form....  An MDS expression in functional form. 
 
      Result..  The compiled and evaluated value of the string with the 
                current values of the arguments. 
 
      Example.  EXECUTE("2+\TOP.XRAY.CHAN01:DATA") is two more than the 
                data of a channel."""
    min_args=1
    max_args=254
    name='EXECUTE'
    opcode=159
    def _evaluate(self):
        ans = COMPILE(*self.args).evaluate().evaluate()
        while isinstance(ans,Builtin):
            ans = ans.evaluate()
        return ans

class EXP(_toBeCompleted):
    """     F90 Mathematical Elemental. 
      
      xponential. 
 
      Argument. X must be real or complex, HC is converted to GC. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to e^X. If X is complex, the 
                imaginary part is in radians. 
 
      Example.  EXP(1.0) is 2.7182818, approximately."""
    min_args=1
    max_args=1
    name='EXP'
    opcode=160

class EXPONENT(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      The exponent part of the argument when 
                represented as a model number. 
 
      Argument. X must be real. Complex type is an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Integer of same shape. 
 
      Result..  The exponent or the model representation with bias 
                removed, provided X is nonzero. For zero, result is zero. 
 
      Examples. Exponent(1.0) is 1 and EXPONENT(4.1) is 3 on the VAX."""
    min_args=1
    max_args=1
    name='EXPONENT'
    opcode=161

class EXTEND(_toBeCompleted):
    """      MDS Operation. 
      
      Removes values not in bounds. 
 
      Arguments Optional: DIM and X. 
        A       MDS signal or dimension or VMS array. 
        DIM     scalar integer from 0 to rank of A less one. 
                Must be 0 or absent for a signal. 
        X       non-complex scalar or array of numbers to check 
                if bounded. 
      Signals.  Same as X. 
      Units...  Same as specified dimension if a signal or dimension. 
      Form....  Shape of X and type from specified dimension. 
 
      Result..  X values that are out of range are replaced 
                by the nearer limit. 
        (i)     If A is an array, the bounds of the array are used. 
        (ii)    If A is a dimension or the specified dimension of a 
                signal, the extreme data value of the axis are used. 
 
      Examples. 
        (i)     EXTEND(1..5,,0..7) is [1,1,2,3,4,5,5,5]. 
        (ii)    EXTEND(BUILD_DIM(BUILD_WINDOW(2,5,1.1), 
                BUILD_RANGE(,,3)),0,5..8) is [7.1,7.1,8.] 
                because the limits are 7.1 and 16.1. 
 
      See also. CULL to eliminate bad values."""
    min_args=1
    max_args=4
    name='EXTEND'
    opcode=391

class EXTRACT(_toBeCompleted):
    """      DCL Character Elemental. 
      
      Extracts an substring from a string starting 
                at an offset. 
 
      Arguments 
        START   integer. 
        LENGTH  integer. 
        STRING  character. 
 
      Signals.  Same as STRING. 
      Units...  Same as STRING. 
      Form....  Character of given length but not less than 0. 
                Compatible shape. 
      Result..  The string from the START-th character (counting from 0) 
                and of LENGTH count is returned. 
                A null string (length is zero) may be returned. 
 
      Examples. EXTRACT(1,2,'A/B/C') is "/B". 
                EXTRACT(4,1,'12') is " "."""
    min_args=3
    max_args=3
    name='EXTRACT'
    opcode=409

class EXT_FUNCTION(_toBeCompleted):
    """      IO.       
      
      Do a FUN, do a routine in an image, or do a command file. 
      
      Usual Form        xxx->yyy(arg...) or _zzz(arg...) 
 
      Methods.  (1) no IMAGE and ROUTINE is a defined function. 
                (2) IMAGE and ROUTINE define an .EXE image with symbol 
                        table and an entry point routine. 
                (3) IMAGE with .FUN extension default and IMAGE filename 
                        define a file of TDISHR commands. 
 
      (1) Arguments     Optional: ARG,... 
        IMAGE   *, a missing argument. 
        ROUTINE Character scalar FUN name previously defined. 
        ARG     As needed by the routine. 
 
      Result..  As defined by the function. 
 
      (2) Arguments     Optional: IMAGE, ARG,... 
        IMAGE   Character scalar filename or *, default MDS$FUNCTIONS. 
        ROUTINE Character scalar entry point name. 
        ARG     As needed by the routine. The forms DESCR, REF, and VAL 
                force passing by descriptor, reference, or long value. 
                These force the DATA of the argument to be evaluated. 
                The default is to pass by whatever descriptor is generated. 
 
      Result..  Function is called like a TDISHR one, i.e., augmented by 
                the output descriptor function. 
      (3) Arguments     Optional: IMAGE, ARG,... 
        IMAGE   Character scalar directory name or *, default MDS$PATH. 
      >>>>>>>>>WARNING, usually MDS$PATH should point the local directory first. 
        ROUTINE Character scalar filename. 
        ARG     Allowed only for a defining FUN. As needed by the routine. 
      >>>>>>>>>WARNING, You must pick a non-conflicting name. The easiest way is 
                to begin both FUN and filename with an underscore (_). 
 
      Result..  The entire file is read (limit 16k bytes) and it is executed. 
                If the compilation was a FUN and IMAGE is missing, 
                the FUN is invoked with arguments. 
                NOTE, The second time around this will use method (1). 
                The result is the last expression evaluated or the returned 
                value of the function. 
 
      Examples  If MDS$PATH is [] and file _FTEST.FUN has: 
                FUN PUBLIC _FTEST(OPTIONAL IN _X) { 
                        IF (PRESENT(_X)) WRITE(*,'_x =',_X); 
                        ELSE WRITE(*,'no argument'); 
                } 
 
                _FTEST(123) returns 17 and prints on the terminal: 
                _x =          123 
 
                If file _OUTER.FUN has: 
                FUN PUBLIC _OUTER(IN _A, IN _B) { 
                RETURN (SPREAD(_A, 0, SIZE(_B)) * SPREAD(_B, 1, SIZE(_A))); 
                } 
 
                _OUTER([1,2,3],[4,5]) is the outer product: 
                [[4,5], [8,10], [12,15]]."""
    min_args=2
    max_args=254
    name='EXT_FUNCTION'
    syntax='image->routine(args) or tdi-fun-name(args)'
    opcode=162

class FCLOSE(_toBeCompleted):
    """      CC IO.    
      
      Close the file unit opened by FOPEN. 
 
      Argument UNIT     long integer pointer from FOPEN. 
 
      Result..  Error code or 0 if none. 
 
      Example.  See FOPEN."""
    min_args=1
    max_args=1
    name='FCLOSE'
    opcode=96

class FINITE(_toBeCompleted):
    """      Logical Elemental. 
      
      Checks that a number is not the reserved real value. 
 
      Argument  X is real. 
 
      Signal..  Same as X. 
      Units...  None. 
      Form....  Logical of same shape as X. 
 
      Result..  Each element of X is checked for validity as a floating 
                point number. All integers are finite. 
 
      Examples. FINITE(1.) is 1BU, FINITE(1./0) is 0BU.    min_args=1"""
    max_args=1
    name='FINITE'
    opcode=410

class FIRSTLOC(_toBeCompleted):
    """      Transformation. 
      
      Locate the leading edges of a set of true 
      elements of a logical mask. 
 
      Arguments Optional: DIM. 
        MASK    logical array. 
        DIM     integer scalar from 0 to n-1, where n is rank of MASK. 
      Signals.  Same as MASK. 
      Units...  None. 
      Form....  Logical of same shape. 
 
      Result. 
        (i)     FIRSTLOC(MASK) has at most one true element. If there is 
                a true value, it is the first in array element order. 
        (ii)    FIRSTLOC(MASK,DIM) is found by applying FIRSTLOC to each 
                of the one-dimensional array sections of MASK that lie 
                parallel to dimension DIM. 
 
      Examples. 
        (i)     First in array order: 
                FIRSTLOC(_M=[0 0 1 0]) is [0 0 0 0]. 
                            [0 1 1 0]     [0 1 0 0] 
                            [0 1 0 1]     [0 0 0 0] 
                            [0 0 0 0]     [0 0 0 0] 
        (ii)    the top edge: 
                FIRSTLOC(_M,0) is [0 0 1 0]. 
                                  [0 1 0 0] 
                                  [0 0 0 1] 
                                  [0 0 0 0]"""
    min_args=1
    max_args=2
    name='FIRSTLOC'
    opcode=164
    CCodeName='FirstLoc'

class FIX_ROPRAND(_toBeCompleted):
    """      Numeric Elemental. 
      
      Fix reserved operand value with substitute. 
      Arguments X and REPLACE must be real or complex. 
 
      Signals.  Single signal or smaller data. 
      Units...  Same as X. 
      Form....  Same as X. 
 
      Result..  Same as X except that elements with $ROPRAND value are 
                replaced by REPLACE. If X is real, the replacement is 
                the real part of REPLACE. If X is complex, the real and 
                imaginary parts are replaced independently. 
 
      Example.  FIX_ROPRAND(1./0.,5) is 5.0."""
    min_args=2
    max_args=2
    name='FIX_ROPRAND'
    opcode=166

class FLOAT(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to real. 
 
      Arguments Optional: KIND. 
        A       numeric. 
        KIND    scalar integer type number, for example, KIND(1d0). 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  If KIND present, the type KIND; otherwise, the real 
                type with the same length. To get F, D, G, or H floating 
                result use F_FLOAT, etc. 
 
      Result..  Immediate at compilation. 
        (i)     A is integer or real, the result is the truncated 
                approximation. 
        (ii)    A is complex, the result is the approximation to the 
                real part. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. FLOAT(-3) is -3.0. FLOAT(Z,Z) is real part of a complex. 
                This is done in TDISHR as REAL(Z). In F90, REAL(Z) sets 
                the default floating point size."""
    min_args=1
    max_args=2
    name='FLOAT'
    opcode=167

class FLOOR(_toBeCompleted):
    """      Numeric Elemental. 
      
      The largest whole number not exceeding the argument. 
 
      Argument. A must be integer or real. Complex numbers are an error. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Same as A. 
 
      Result..  For integer A, no change. For real A>=0, AINT(A). For 
                real A<0, A if AINT(A)==A and AINT(A)-1 otherwise. 
 
      See also. CEILING and NINT. 

      Examples. FLOOR(2.783) is 2.0. FLOOR(-2.783) is -3.0."""
    min_args=1
    max_args=1
    name='FLOOR'
    opcode=168

class FOPEN(_toBeCompleted):
    """      CC IO.    
      
      Open a file name. 
 
      Arguments 
        FILENAME character scalar with node, disk, file, and extension. 
        MODE    character scalar: r for read, w for write, a for append, 
                and + for update may be added. Note lowercase. 
 
      Result..  Integer scalar, a pointer to a FILE block. 
 
      Examples..
         to write.. _u=FOPEN('myfile.ext','w'),WRITE(_u,_var),FCLOSE(_u). 
	 to read    _u=FOPEN('myfile.ext','r'),_var=READ(_u),FCLOSE(_u)."""
    min_args=2
    max_args=254
    name='FOPEN'
    opcode=265

class FOR(_toBeCompleted):
    """FOR ([INIT],[TEST],[UPDATE],STMT...)
      CC Statement. 
      
      Initialize, test, and update a loop. 
      
      Required Usual Form. FOR (INIT; TEST; UPDATE) STMT. 
      Function Form     FOR([INIT],[TEST],[UPDATE],STMT...). 
                May be syntatically invalid. 
 
      Arguments Optional: INIT, TEST, UPDATE. 
        INIT    any expression. 
        TEST    logical scalar. 
        UPDATE  any expression. 
        STMT    statement, simple or compound (like {S1 S2}). 
      >>>>>>WARNING, multiple statements (like S1 S2) in call form are 
                considered to be in braces. 
 
      Result..  None. 
 
      Example.  FOR (_J=DSIZE(_X); --_J>=0; ) IF(_X[_J]) BREAK;"""
    min_args=4
    max_args=254
    name='FOR'
    opcode=169

class FRACTION(_toBeCompleted):
    """      F90 Numeric Elemental. Fractional part of the model representation of 
                the argument value. 
 
      Argument. X must be real or complex. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Same as X. 
 
      Result..  The value of X with the exponent set to its bias value. 
 
      Example.  FRACTION(3.0) is 0.75 on the VAX.""" 
    min_args=1
    max_args=1
    name='FRACTION'
    opcode=170

class FSEEK(_toBeCompleted):
    """      CC IO     
      
      Position a file pointer. 
 
      Arguments Optional: OFFSET, ORIGIN. 
        UNIT    Integer scalar pointer from FOPEN. 
        OFFSET  Long scalar offset (w.r.t. ORIGIN) of file position. 
        ORIGIN  Scalar number: 0 for absolute (w.r.t. beginning of file), 
                1 for relative to current position, 2 for offset from 
                end of file. 
 
      Result..  Error code or 0 if none. 
      >>>>>>WARNING, does not work properly for "record" files, only stream 
                     files."""
    min_args=1
    max_args=3
    name='FSEEK'
    opcode=309

class FS_COMPLEX(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to IEEE single precision floating complex (32-bit x 2). 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  F-precision real of same shape. 
 
      Result..  Integers, reals and the real part of complex numbers are 
                converted to F-precision reals. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  FS_COMPLEX(12,1), FS_FLOAT(12.,1) FS_FLOAT(12H0,1) are CMPLX(12.0,1) 
                approximately."""
    
    min_args=1
    max_args=2
    name='FS_COMPLEX'
    opcode=451
    CCodeName='FS_complex'

class FS_FLOAT(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to IEEE single precision floating real (32-bit) 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  F-precision real of same shape. 
 
      Result..  Integers, reals and the real part of complex numbers are 
                converted to F-precision reals. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  FS_FLOAT(12), FS_FLOAT(12.) FS_FLOAT(12H0) are 12.0, 
                approximately."""
    min_args=1
    max_args=1
    name='FS_FLOAT'
    opcode=450
    CCodeName='FS_float'

class FTELL(_toBeCompleted):
    """      CC IO     
      
      Report position of a file pointer. 
 
      Argument UNIT     Integer scalar pointer from FOPEN. 
 
      Result..  Error code or 0 if none. 
      >>>>>>WARNING, does not work properly for "record" files, only stream  
                     files."""
    min_args=1
    max_args=1
    name='FTELL'
    opcode=417

class FT_COMPLEX(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to IEEE double precision floating complex (64-bit x 2). 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  real of same shape. 
 
      Result..  Integers, reals and the real part of complex numbers are 
                converted to double precision reals. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  FT_COMPLEX(12,1), FT_FLOAT(12.,1) FT_FLOAT(12H0,1) are CMPLX(12.0,1) 
                approximately."""
    min_args=1
    max_args=2
    name='FT_COMPLEX'
    CCodeName='FT_complex'
    opcode=453

class FT_FLOAT(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to IEEE double precision floating real (64-bit) 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  real of same shape. 
 
      Result..  Integers, reals and the real part of complex numbers are 
                converted to double precision reals. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  FT_FLOAT(12), FT_FLOAT(12.) FT_FLOAT(12H0) are 12.0, 
                approximately."""
    min_args=1
    max_args=1
    name='FT_FLOAT'
    CCodeName='FT_float'
    opcode=452

class FUN(_toBeCompleted):
    """      Description. 
      
      Define a function, its argument form, and the action 
                taken or invoke a function. 
      
      Usual Definition. FUN NAME([ARG],...) STMT 
                FUN PRIVATE NAME([ARG],...) STMT 
                FUN PUBLIC NAME([ARG],...) STMT. 
      Usual Invocation. NAME([X],...) 
                PRIVATE NAME([X],...) 
                PUBLIC NAME([X],...). 
      Function Form     FUN(NAME,STMT,[ARG],...) May be syntatically invalid. 
                FUN(PRIVATE(NAME),STMT,[ARG],...) 
                FUN(PUBLIC(NAME),STMT,[ARG],...). 
 
      Arguments Optional: ARG,... X,.... 
        NAME    an alphanumeric name beginning with an underscore or a 
                dollar sign. The name defined and invoke must match 
                exactly. NAME may be preceded by PRIVATE or PUBLIC to 
                specify the scope of its definition. Default is PRIVATE. 
                A PRIVATE FUN is seen only by the routine defining it. 
                A PUBLIC FUN is seen by all routines. 
        ARG,... an alphanumeric name beginning with an underscore or a 
                dollar sign that will define the variable referenced in 
                STMT. Each argument may have modifiers IN, INOUT, or OUT 
                to specify the transfer of data between the calling and 
                the called routines. OPTIONAL may precede a modifier or 
                the variable name in an ARG. ARG marked as IN should not 
                be modified in STMT and never changes the actual input. 
                The default mode is IN. 
        STMT    a statement form. 
      >>>>>>>>>WARNING, use care in tree pathnames used in PUBLIC FUN, they 
                will be relative to invocation, not to the definition. 
                PRIVATE FUN invocations are, of necessity, at that node. 
        X,...   the actual instance of the arguments in the calling 
                routine. If the corresponding ARG is marked as INOUT or 
                OUT this must be a variable. If the corresponding ARG is 
                not marked OPTIONAL, then that X must be present and not 
                null. 
 
      Side Effect. NAME is allocated, any prior value is freed. 
      Result..  The argument expression of a RETURN statement or none. 
 
      Example.  To create a function 
                FUN _SINCOSD(IN _ANGLE, OUT _SIN, OPTIONAL OUT _COS) { 
                        _SIN = SIND(_ANGLE); 
                        IF (PRESENT(_COS)) _COS = COSD(_ANGLE); 
                } 
                Then _SINCOSD(30,_Y,_X) sets _Y to 0.5 and _X to 
                0.8660254. This has no functional result. 
 
 
      Additional information available: 
 
      IN NAME    INOUT NAME OPTIONAL NAME         OUT NAME 
 
	      IN NAME 
 
	        FUN mode. Defines argument that is evaluated but not rewritten. 
 
	        Argument.       NAME must be a variable name. 
 
	      INOUT NAME 
 
	        FUN mode. Defines argument that is evaluate and rewritten when 
	                        the FUN finishes. 
 
	        Argument.       NAME must be a variable name. 
 
 
	      OPTIONAL NAME 
 
	        FUN mode. Defines argument that may be omitted in actual call. 
 
	        Argument.       NAME must be a variable name, or IN, INOUT, or OUT 
	                        before a name. 
 
 
	      OUT NAME 
 
	        FUN mode. Defines argument that is not evaluated, begins as undefined 
	                        in the FUN and is written when the FUN finishes. 
 
	        Argument.       NAME must be a variable name."""
    min_args=2
    max_args=254
    name='FUN'
    syntax='FUN name(arglist){statements}'
    opcode=171

class F_COMPLEX(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to F-precision floating complex. 
 
      Arguments Optional: Y. 
        X       numeric. 
        Y       numeric. Default is zero. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  F-precision complex of compatible shape. 
 
      Result..  If Y is absent and X is complex, the AIMAG(X) is used 
                for Y. If X and Y are present, the real parts of each 
                are used. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
      Example.  F_COMPLEX(3,4.1D0) is CMPLX(3.0,4.1), approximately."""
    min_args=1
    max_args=2
    name='F_COMPLEX'
    opcode=172

class F_FLOAT(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to F-precision (OpenVMS) floating real. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  F-precision real of same shape. 
 
      Result..  Integers, reals and the real part of complex numbers are 
                converted to F-precision reals. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  F_FLOAT(12), F_FLOAT(12.) F_FLOAT(12H0) are 12.0, 
                approximately."""
    min_args=1
    max_args=1
    name='F_FLOAT'
    opcode=173

class GE(_toBeCompleted):
    """      Logical Elemental. 
      
      Tests for first greater than or equal to second. 
      
      Usual Forms       X >= Y, X GE Y. 
      Function Form     GE(X,Y). 
 
      Arguments X and Y must both be numeric or character. 
                Complex numbers are an error. 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
      Result..  True if X is greater than or equal to Y; otherwise, 
                false. A reserved operand is always false. Character are 
                compared in the processor collating sequence. 
      >>>>>>>>>WARNING, floating point operations may not match an exact 
                calculation for nonterminating binary fractions. You 
                cannot predict that .1+.1>=.2 is true. Integer values 
                may be truncated when matched to floating numbers. 
 
      Example.  2>=2.0 is $TRUE."""
    min_args=2
    max_args=2
    name='GE'
    opcode=174

class GETDBI(_toBeCompleted):
    """      MDS Operation. 
      
      Get database information. 
      
      Arguments Optional: INDEX. 
        STRING  character scalar. The string may be 
                abbreviated in upper or lower case to any unique form. 
 
        Logical         OPEN_FOR_EDIT   modifiable 
                        MODIFIED        changes made 
        Long            SHOTID          shot number 
                        NUMBER_OPENED   database pointers active 
                        MAX_OPEN        database pointers allowed 
        Character       NAME            experiment name 
                        DEFAULT         default/current node 
        INDEX   integer scalar less than MAX_OPEN value. 
                Determines which tree location is reported. 
                The default value of 0 is the current tree. 
 
      Result..  Depends on the experiment, shot number, and history. 
 
      See also. $DEFAULT, $EXPT, $SHOT, and $SHOTNAME constants."""
    min_args=1
    max_args=2
    name='GETDBI'
    CCodeName='GetDbi'
    opcode=389

class GETNCI(_toBeCompleted):
    """      MDS Operation. 
      
      Get node characteristic information about tree elements. 
      Arguments Optional: NODE and USAGE. 
        NODE    a NID or long node identifier or a PATH or character 
                form of the path of a tree element--child or member, or 
                a wildcarded path. May be an array. 
                Default is current position in tree. 
      >>>>>>>>>WARNING, path names are case-sensitive. 
        STRING  character scalar. The string may be abbreviate in upper 
                or lower case to any unique form. Case-insensitive. 
        USAGE   character scalar or vector. This limits the search of 
                NODE names. It must be a valid usage name like "ALL", 
                "ANY", or "TEXT". 

 
                The STRING names by returned type follow. 
Byte unsigned	 CLASS	 storage classification
DTYPE	 storage data type
USAGE	 allowed data type
Character	 FULLPATH	 path from top of tree
MINPATH	 shortest relative path
NODE_NAME	 last part of pathname
ORIGINAL_PART_NAME	 Original node name in device
PATH	 path from top or tag
Logicals	 COMPRESSIBLE	 has arrays
COMPRESS_ON_PUT	 use comprssion on put
DO_NOT_COMPRESS	 no compression allowed
ESSENTIAL	 node is essential
IS_CHILD	 parent relationship
IS_MEMBER	 parent relationship
NID_REFERENCE	 contains nid references
NO_WRITE_MODEL	 write to model disabled
NO_WRITE_SHOT	 write to shot disabled
PARENT_STATE	 parent on or off
PATH_REFERENCE	 contains path references
SETUP_INFORMATION	 has setup operations
STATE	 on or off
USAGE_ACTION	 allows only action
USAGE_ANY	 allows any data
USAGE_AXIS	 allows only axis
USAGE_COMPOUND_DATA	 allows only compound_data
USAGE_DEVICE	 allows only conglomerate
USAGE_DISPATCH	 allows only dispatch
USAGE_NUMERIC	 allows VMS data
USAGE_SIGNAL	 allows only signal
USAGE_STRUCTURE	 allows no data, was NONE
USAGE_SUBTREE	 allows only subtree
USAGE_TASK	 allows only task
USAGE_TEXT	 allows only text
USAGE_WINDOW	 allows only window
WRITE_ONCE	 change only once
Long	 DEPTH	 tree parents above
LENGTH	 data size
NID_NUMBER	 tree logical offset
NUMBER_OF_CHILDREN	 number of child nodes
NUMBER_OF_MEMBERS	 number of member nodes
PARENT_RELATIONSHIP	 child or member
Long unsigned	 GET_FLAGS	 bit flags
OWNER_ID	 rights identifier
STATUS	 status
NID	 BROTHER	 next child or member
CHILD	 first child
MEMBER	 first member
PARENT	 the one above in tree
NID arrays	 CHILDREN_NIDS	 list of children
CONGLOMERATE_NIDS
MEMBER_NIDS	 list of members
Quadword unsigned	 TIME_INSERTED	 VMS date and time
Word unsigned	 CONGLOMERATE_ELT	 number of elements
Node data	 RECORD	 actual data

 
      Signals.  None, except for RECORD. 
      Units...  None, except for RECORD. 
      Form....  VECTOR concatenation of all elements found for the list 
                of NIDs and PATHs. Scalar for non-array results of 
                single input. All data types are the same for one 
                request except possibly for RECORD. Character names vary 
                in length except for NODE_NAME, which has length 12. 
 
      Result..  A scalar or simple vector list of results. RECORD may 
                not be able to VECTOR the results of a list of 
                NIDs/PATHs. Logicals allow easy testing of bit or value. 
      >>>>>>>>>WARNING, only GETNCI can handle arrays of NIDs/PATHs. 
      >>>>>>>>>WARNING, a NID/PATH result used in an expression will have its 
                data taken--just as if the node name had been used. 
                Thus GETNCI(\TOP.XRAY,"MEMBER")//" Z" might be 
                "Xray diagnostic Z" if the first member were the 
                description. 
 
      Example.  GETNCI(\TOP.XRAY,"PARENT") is \TOP as is 
                GETNCI("\TOP.XRAY","par")."""
    min_args=2
    max_args=3
    name='GETNCI'
    CCodeName='GetNci'
    opcode=175

class GOTO(_toBeCompleted):
    """      CC Statement. 
      
      Branch to label. 
      
      Usual Form        GOTO NAME;. 
      Function Form     GOTO(NAME). Decompiles to usual form. 
 
      Argument. NAME must be character with name of a label in the 
                local code. 
 
      Result..  None. 
 
      Example.  IF (_X[2]) GOTO _MYLABEL; 
                ... 
                LABEL _MYLABEL : ... ."""
    min_args=1
    max_args=1
    name='GOTO'
    opcode=176

class GT(_toBeCompleted):
    """      Logical Elemental. 
      
      Tests for first greater or equal to second. 
      
      Usual Forms       X > Y, X GT Y. 
      Function Form     GT(X,Y). 
 
      Arguments X and Y must both be numeric or character. 
                Complex numbers are an error. 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if X is greater than Y; otherwise, false. A 
                reserved operand is always false. Character are compared 
                in the processor collating sequence. 
      >>>>>>>>>WARNING, floating point operations may not match an exact 
                calculation for nonterminating binary fractions. You 
                cannot predict that .1+.1>=.2 is true. Integer values 
                may be truncated when matched to floating numbers. 
 
      Example.  2>2.0 is $FALSE."""
    min_args=2
    max_args=2
    name='GT'
    syntax='arg0 > arg1, arg0 gt arg1'
    opcode=177

class G_COMPLEX(_toBeCompleted):
    """      Conversion Elemental.
      
      Convert to G-precision floating complex. 
 
      Arguments Optional: Y. 
        X       numeric. 
        Y       numeric. Default is zero. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  G-precision complex of compatible shape. 
 
      Result..  If Y is absent and X is complex, the AIMAG(X) is Y. 
                If X and Y are present, the real parts of each are used. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  G_COMPLEX(3,4.1) is CMPLX(3.0G0,4.1G0), approximately."""
    min_args=1
    max_args=2
    name='G_COMPLEX'
    opcode=178

class G_FLOAT(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to G-precision floating real. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  G-precision real of same shape. 
 
      Result..  Integers, reals and the real part of complex numbers are 
                converted to G-precision reals. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  G_FLOAT(12), G_FLOAT(12.) G_FLOAT(12H0) are 12.0G0, 
                approximately."""
    min_args=1
    max_args=1
    name='G_FLOAT'
    opcode=179

class HELP_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the help field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_PARAM, the help field, textual information. 
                Otherwise, an error. 
 
      Example.  HELP_OF(BUILD_PARAM(42,"the answer",$VALUE>6)) is 
                "the answer". 
      See also. $VALUE and $THIS for use of this within a parameter."""
    min_args=1
    max_args=1
    name='HELP_OF'
    opcode=180

class HUGE(_completed):
    """      F90 Inquiry. 
      
      The largest number in the model representing numbers of 
                the same type as the argument. 
 
      Argument. X must be numeric scalar or array. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Scalar of same type as real part of X. 
      Result..  The result is r^q - 1 if X is integer and 
                (1-(b^-p))b^emax if X is real, where r is the integer 
                base, q is the number of digits, b is the real base, p 
                is the number of digits, emax is the maximum exponent in 
                model numbers like X. 
 
      Examples. HUGE(1.0) is (1-(2^-24))*2^127 and 
                HUGE(0) is 2^31-1 on the VAX."""
    min_args=1
    max_args=1
    name='HUGE'
    opcode=181
    def _evaluate(self):
        def getMax(v):
            if isinstance(v,_NP.floating):
                ans=self.makeData(_NP.finfo(v).max)
            elif isinstance(v,_NP.integer):
                ans=self.makeData(type(v)(_NP.iinfo(v).max))
            elif isinstance(v,_NP.ndarray):
                ans = getMax(v.flat[0])
            elif isinstance(v,_data.Signal):
                ans = getMax(v.value)
            else:
                raise _data.TdiException('Invalue argument type: %s' % (str(type(v)),))
            return ans
        return getMax(_dataArg(self.args[0]))

class H_COMPLEX(_toBeCompleted):
    """      Conversion Elemental.
      
      Convert to H-precision floating complex. 
 
      Arguments Optional: Y. 
        X       numeric. 
        Y       numeric. Default is zero. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  H-precision complex of compatible shape. 
 
      Result..  If Y is absent and X is complex, the AIMAG(X) is Y. 
                If X and Y are present, the real parts of each are used. 
                Immediate at compilation. 
 
      Example.  H_COMPLEX(3,4.1) is CMPLX(3.0H0,4.1H0), approximately."""
    min_args=1
    max_args=2
    name='H_COMPLEX'
    opcode=182

class H_FLOAT(_toBeCompleted):
    """      Conversion Elemental.
      
      Convert to H-precision floating real. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  H-precision real of same shape. 
 
      Result..  Integers, reals and the real part of complex numbers are 
                converted to H-precision reals. 
                Immediate at compilation. 
 
      Example.  H_FLOAT(12), H_FLOAT(12.) H_FLOAT(12H0) are 12.0H0, 
                approximately."""
    min_args=1
    max_args=1
    name='H_FLOAT'
    opcode=183

class IACHAR(_toBeCompleted):
    """      F90 Character Elemental.
      
      The position of a character in the ASCII 
                collating sequence. 
 
      Argument. C must be a length-one character. 
 
      Signals.  Same as C. 
      Units...  Same as C. 
      Form....  Byte unsigned of same shape. 
 
      Result..  The position of C in the ASCII collating sequence, where 
                0<=IACHAR(C)<=127; otherwise, a processor value. If 
                LLE(C,D) is true then IACHAR(C)<=IACHAR(D) for all 
                represented characters. 
 
      See also. ICHAR and the inverses ACHAR and CHAR. 

      Example.  IACHAR('X') is 88BU."""
    min_args=1
    max_args=1
    name='IACHAR'
    opcode=184

class IAND(_toBeCompleted):
    """      F90 Bit-wise Elemental. 
      
      Bit-by-bit intersection. 
      
      Usual Form        I & J. 
      Function Form     IAND(I,J). 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  True for each bit true in I and J; otherwise, false. 
 
      Example.  IAND(3,5) is 1."""
    min_args=2
    max_args=2
    name='IAND'
    syntax='arg0 & arg1'
    opcode=185

class IAND_NOT(_toBeCompleted):
    """      Bit-wise Elemental. 
      
      Bit-by-bit intersection with the J complemented. 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  True for each bit of I true and of J false; otherwise, 
                false. 
 
      Example.  IAND_NOT(3,5) is 2."""
    min_args=2
    max_args=2
    name='IAND_NOT'
    opcode=186

class IBCLR(_toBeCompleted):
    """      F90 Bit-wise Elemental.
      
      Clear one bit to zero. 
 
      Arguments 
        I       any. F90 requires integer. 
        POS     integer offset within the element of I, must be 
                nonnegative and less than BIT_SIZE(I). 
 
      Signals.  Same as I. 
      Units...  Same as I. 
      Form....  Same type as I, compatible shape. 
 
      Result..  Same as I with bit at offset POS cleared. 
 
      Examples. IBCLR(14, 1) is 12. 
                IBCLR(31,[1,2,3,4]) is [29,27,23,15]. 
 
      See also. IBSET to set, IBITS to extract, and BTEST to test."""
    min_args=2
    max_args=2
    name='IBCLR'
    opcode=63

class IBSET(_toBeCompleted):
    """      Bit-wise Elemental.
      
      Set a bit to one. 
 
      Arguments 
        I       any. F90 requires integer. 
        BIT     integer offset within the element of I. Must be 
                nonnegative and less than BIT_SIZE(I). 
 
      Signals.  Same as I. 
      Units...  Same as I. 
      Form....  Same type as I, compatible shape. 
 
      Result..  Same as I with bit at offset BIT set. 
 
      Examples. IBSET(12,1) is 14. 
                IBSET(0,[1,2,3,4]) is [2,4,8,16]. 
 
      See also. IBCLR to clear, IBITS to extract, and BTEST to test."""
    min_args=2
    max_args=2
    name='IBSET'
    opcode=68

class ICHAR(_toBeCompleted):
    """      F90 Character Elemental.
      
      The position of a character in the 
      	processor collating sequence. 
 
      Argument. C must be a length-one character. 
 
      Signals.  Same as C. 
      Units...  Same as C. 
      Form....  Byte unsigned of same shape. 
 
      Result..  The position of C in the processor collating sequence 
                and is in the range 0<=ICHAR(C)"""
    min_args=1
    max_args=1
    name='ICHAR'
    opcode=187

class IDENT_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the ident field. 
 
      Argument. Descriptor as below. 
 
      Result..  DISPATCH_OF(A) is searched for this: 
                DSC$K_DTYPE_DISPATCH, the ident field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='IDENT_OF'
    opcode=188

class IEOR(_toBeCompleted):
    """      F90 Bit-wise Elemental. 
      
      Bit-by-bit exclusive-OR. 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  True for exactly one bit of I and J true; 
                otherwise, false. 
 
      Example.  IEOR(1,3) is 2."""
    min_args=2
    max_args=2
    name='IEOR'
    opcode=210

class IEOR_NOT(_toBeCompleted):
    """      F90 Bit-wise Elemental. Bit-by-bit exclusive-OR with the second 
                complemented. Equivalent to INOT(IEOR(I,J)). 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  False for each bit of I equal to that bit of J; 
                otherwise, true. 
 
      Example.  IEOR_NOT(1bu,3bu) in binary is 0B11111101BU"""
    min_args=2
    max_args=2
    name='IEOR_NOT'
    opcode=211

class IF(_toBeCompleted):
    """      CC Statement. 
      
      Do statement if expression true, else possibly do another. 
      
      Required Usual Forms. IF (TEST) STMT, IF (TEST) STMT ELSE ELSESTMT. 
      Function Form.    IF(TEST,STMT,[ELSESTMT]). May be syntatically invalid. 
 
      Arguments Optional: ELSESTMT. 
        TEST    logical scalar. 
        STMT    statement, simple or {brace enclosed}. 
        ELSESTMT statement, simple or {brace enclosed}. 
 
      Result..  None. 
 
      Example.  IF (_A) _B=2; ELSE _B=3;."""
    min_args=2
    max_args=3
    name='IF'
    syntax='if (condition) {statements} [else {statements}]'
    opcode=189

class IF_ERROR(_toBeCompleted):
    """      Miscellaneous.
      
      Evaluate arguments until no error. 
 
      Arguments Are any expressions. 
 
      Result..  That of the first expression without an error. If all 
                have errors, the result is the final error. 
 
      Example.  IF_ERROR(_A EQ _B, _A, _B) gives the expression if _A 
                and _B are defined or the one defined; else an error."""
    min_args=1
    max_args=254
    name='IF_ERROR'
    opcode=190

class IMAGE_OF(_PART_OF):
    """      MDS Operation.
      
      Get the image field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_CALL, the image field. 
                DSC$K_DTYPE_CONGLOM, the image field. 
                DSC$K_DTYPE_ROUTINE, the image field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='IMAGE_OF'
    opcode=191

class IN(_toBeCompleted):
    """Used in FUN definition to denote argument is readonly.

       Example: PUBLIC FUN _GUB(IN _a)"""
    min_args=1
    max_args=1
    name='IN'
    syntax="IN _arg"
    opcode=192

class INAND(_toBeCompleted):
    """      Bit-wise Elemental.
      
      Complement of bit-by-bit intersection. 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  False for each bit true in I and J; otherwise, true. 
 
      Example.  INAND(3BU,5BU) in binary is 0B111111110BU."""
    min_args=2
    max_args=2
    name='INAND'
    opcode=193

class INAND_NOT(_toBeCompleted):
    """      Bit-wise Elemental.
      
      Complement of bit-by-bit intersection with the 
                second complemented. Equivalant to IOR(INOT(I),J). 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  False for each bit of I true and of J false; otherwise, 
                true. 
      Example.  INAND_NOT(3WU,5WU) in binary is 0B11111101BU."""
    min_args=2
    max_args=2
    name='INAND_NOT'
    opcode=194

class INDEX(_toBeCompleted):
    """      F90 Character Elemental.
      
      The starting position of a substring within 
                a string. Note the result is 1 less than for F90. 
 
      Arguments Optional: BACK 
        STRING  character. 
        SUBSTRING character. 
        BACK    logical. 
 
      Signals.  Single signal or smallest data. 
      Units...  Same as STRING. 
      Form....  Integer of compatible shape. 
 
      Result. 
        (i)     If BACK is absent or is false, the minimum value j such 
                that STRING(j:j+LEN(SUBSTRING-1)==SUBSTRING or -1 if 
                there is no such value. 
                For LEN(STRING) < LEN(SUBSTRING), the result is -1 
                and for LEN(SUBSTRING) = 0, the result is 0. 
        (ii)    If BACK present and true, the maximum value j as above 
                or -1 if there is no such value. 
                For LEN(STRING) < LEN(SUBSTRING), the result is -1 
                and for LEN(SUBSTRING) = 0, the result is 0. 
 
      Examples. INDEX('FORTRAN','R') is 2. 
                INDEX('FORTRAN','R',$TRUE) is 4."""
    min_args=2
    max_args=3
    name='INDEX'
    opcode=195

class INOR(_toBeCompleted):
    """      Bit-wise Elemental.
      
      Complement of bit-by-bit union. 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  False for either bit true in I and J; otherwise, true. 
 
      Example.  INOR(3BU,5BU) in binary is 0B11111000BU."""
    min_args=2
    max_args=2
    name='INOR'
    opcode=196

class INOR_NOT(_toBeCompleted):
    """      Bit-wise Elemental.
      
      Complement of bit-by-bit union with the 
                second complemented. Equivalant to IAND(NOT(I),J). 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  False for each bit of I true or of J false; otherwise, 
                true. 
 
      Example.  INOR_NOT(3BU,5BU) in binary is 0B00000100BU."""
    min_args=2
    max_args=2
    name='INOR_NOT'
    opcode=197

class INOT(_toBeCompleted):
    """      Bit-wise Elemental.
      
      Complement bit-by-bit the argument. 
      
      Usual Form        ~ J. 
      Function Form     INOT(J). 
 
      Argument. J must be integer. 
 
      Signals.  Same as J. 
      Units...  Same as J. 
      Form....  Unsigned integer of same shape. 
      Result..  Each binary bit is negated. 
      >>>>>>>>>WARNING, F90 calls this NOT, we cannot. 
 
      Example.  INOT(5BU) in binary is 0B11111010."""
    min_args=1
    max_args=1
    name='INOT'
    opcode=198
    syntax='~arg0'

class INOUT(_toBeCompleted):
    """Used in FUN definitions to indicate that argument is used for input and output

       Example: PUBLIC FUN _MYFUN(INOUT _ARG)"""
    min_args=1
    max_args=1
    name='INOUT'
    syntax="INOUT _arg"
    CCodeName='InOut'
    opcode=199

class INT(_toBeCompleted):
    """      Conversion Elemental.
      
      Convert to integer. 
 
      Arguments A must numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  The integer type with the same length.  
 
      Result..  Immediate at compilation. 
        (i)     A is integer or real, the result is the truncated 
                approximation to the low-order part of the integer. 
        (ii)    A is complex, the result is the approximation to the 
                real part. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  INT(2.783) is 2."""
    min_args=1
    max_args=2
    name='INT'
    opcode=201

class INTERRUPT_OF(_PART_OF):
    """      MDS Operation.
      
      Get the interrupt field. 
 
      Argument. Descriptor as below. 
 
      Result..  DISPATCH_OF(A) is searched for this: 
                DSC$K_DTYPE_DISPATCH, the interrupt field. 
                The dispatch qualifier must be TREE$K_SCHED_ASYNC 
                and the result must evaluate to text DSC$K_DTYPE_T. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='INTERRUPT_OF'
    opcode=443

class INT_UNSIGNED(_toBeCompleted):
    """      Conversion Elemental.
      
      Convert to unsigned integer. 
 
      Arguments A must numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  The integer type with the same length. To get specific 
                unsigned integer types use BYTE_UNSIGNED, WORD_UNSIGNED, 
                LONG_UNSIGNED, QUADWORD_UNSIGNED, or OCTAWORD_UNSIGNED. 
 
      Result..  Immediate at compilation. 
        (i)     A is integer or real, the result is the truncated 
                approximation to the low-order part of the integer. 
        (ii)    A is complex, the result is the approximation to the 
                real part. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  INT_UNSIGNED(2.783) is 2LU."""
    min_args=1
    max_args=1
    name='INT_UNSIGNED'
    opcode=205

class IOR(_toBeCompleted):
    """      F90 Bit-wise Elemental.
      
      Bit-by-bit inclusive OR. 
      
      Usual Form        I | J. 
      Function Form     IOR(I,J) 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  True for either bit true in I and J; otherwise, false. 
      Example.  IOR(1,3) is 3."""
    min_args=2
    max_args=2
    name='IOR'
    syntax='arg0 | arg1'
    opcode=207

class IOR_NOT(_toBeCompleted):
    """      Bit-wise Elemental.
      
      Bit-by-bit union with the second complemented. 
 
      Arguments I and J must be integers. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Unsigned integer of compatible shape. 
 
      Result..  True for each bit of I true or of J false; otherwise, 
                false. 
 
      Example.  IOR_NOT(3BU,5BU) in binary is 0B11111011BU"""
    min_args=2
    max_args=2
    name='IOR_NOT'
    opcode=208

class ISHFT(_toBeCompleted):
    """      F90 Numeric Elemental.
      
      Logical shift of an element. 
 
      Arguments 
        I       must be integer. Octaword is not supported. 
        SHIFT   must be integer. The low byte is used. 
 
      Signals.  Single signal or smaller data. 
      Units...  Same as I. 
      Form....  Type of I, compatible shape of all. 
 
      Result..  The bits of I shifted SHIFT positions left if positive 
                or -SHIFT positions right for SHIFT negative. The 
                vacated bits are cleared. 
 
      Example.  ISHFT(3,1) is 6."""
    min_args=2
    max_args=2
    name='ISHFT'
    opcode=312

class I_TO_X(_toBeCompleted):
    """      MDS Transform Elemental.
      
      Convert index into axis values. 
 
      Arguments Optional I. 
        DIMENSION a dimension with optional window and required axis. 
                If DIMENSION is missing, the unchanged I is returned. 
                If the window of DIMENSION is missing, the first 
                axis point is assigned an index of 0. 
        I       scalar or array list of axis integer-like values. 
                (For TDI$I_TO_X, the fake address of -1 for I, 
                returns a 2-element vector with the axis bounds.) 
 
      Signals.  Same as I. 
      Units...  Same as axis of DIMENSION. 
      Form....  Same type as DATA(axis). Same shape as I. 
 
      Result..  The window and axis are evaluated for each index point. 
                Although the window start and end indices may be used 
                to determine the value of axis points, they do not 
                limit the range of results. 
 
      Examples. I_TO_X(BUILD_DIM(BUILD_WINDOW(2,5,1.1),BUILD_RANGE(,, 
                3))) is Set_Range(2:5,[7.1,10.1,13.1,16.1]). 
                I_TO_X(BUILD_DIM(BUILD_WINDOW(2,7,1.1),BUILD_RANGE(,, 
                3)),1..4) is Set_Range(1:4,[4.1,7.1,10.1,13.1]). 
                The index 1 (axis point 4.1) is outside the valid 
                window of 2 to 7. 
 
      See also. CULL and EXTEND to discard or limit axis points. 
                X_TO_I for the inverse transform. 
                NINT to round indices to the nearest integers. 
                SUBSCRIPT where this is used for ranges."""
    min_args=1
    max_args=2
    name='I_TO_X'
    CCodeName='ItoX'
    opcode=392

class KIND(_toBeCompleted):
    """      MDS/VMS Inquiry. 
      
      Data type of data storage descriptor. 
 
      Argument. A may be any descriptor. 
 
      Result..  Byte unsigned of the descriptor data type. 
                Descriptor data types (DSC$K_DTYPE_DSC) are removed. 
                Use KIND for data type without NID, PATH, or variable. 
                Use KIND_OF for data type including them. 
 
      Examples. KIND(3) is 8 (DSC$K_DTYPE_L) on the VAX. 
                KIND(1.2) is 10 (DSC$K_DTYPE_F) on the VAX. 
                KIND(_X) is the kind of the value in variable _X."""
    min_args=1
    max_args=1
    name='KIND'
    opcode=137

class KIND_OF(_toBeCompleted):
    """      MDS/VMS Inquiry. 
      
      Data type of data storage descriptor. 
 
      Argument. A may be any descriptor. 
 
      Result..  Byte unsigned of the descriptor data type. 
                Descriptor data types (DSC$K_DTYPE_DSC) are removed. 
                Use KIND for data type without NID, PATH, or variable. 
                Use KIND_OF for data type including them. 
 
      Examples. KIND_OF(3) is 8 (DSC$K_DTYPE_L) on the VAX. 
                KIND_OF(1.2) is 10 (DSC$K_DTYPE_F) on the VAX. 
                KIND_OF(_X) is 191 (DSC$K_DTYPE_IDENT) on the VAX."""
    min_args=1
    max_args=1
    name='KIND_OF'
    opcode=437

class LABEL(_toBeCompleted):
    """      Modified CC Statement. 
      
      Label holder for statements. 
      
      Required Usual Form. LABEL NAME : STMT. 
      Functiom Form     LABEL(NAME,STMT,...). May be syntatically invalid. 
 
      Arguments 
        NAME    character scalar. Should begin with underscore (_). 
        STMT    statement, simple or compound (like {S1 S2} or 
                multiple (like S1 S2). 
 
      Result..  STMT ignored except in a GOTO that does not match 
                the LABEL. 
      Example.  IF (_A > 0) GOTO _XX 
                ... 
                LABEL _XX : ..."""
    min_args=2
    max_args=254
    name='LABEL'
    syntax='LABEL _gub :'
    opcode=212

class LANGUAGE_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the language field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_PROCEDURE, the language field. 
                Otherwise, an error. """
    min_args=1
    max_args=1
    name='LANGUAGE_OF'
    opcode=214

class LASTLOC(_toBeCompleted):
    """      Transformation. 
      
      Locate the trailing edges of a set of 
                true elements of a logical mask. 
 
      Arguments Optional: DIM. 
        MASK    logical array. 
        DIM     integer scalar from 0 to n-1, where n is rank of MASK. 
 
      Signals.  Same as MASK. 
      Units...  None. 
      Form....  Logical of same shape. 
 
      Result. 
        (i)     LASTLOC(MASK) has at most one true element. If there is 
                a true value, it is the first in array element order. 
        (ii)    LASLOC(MASK,DIM) is found by applying LASTLOC to each of 
                the one-dimensional array sections of MASK that lie 
                parallel to dimension DIM. 
 
      Examples. 
        (i)     The last array-ordered element 
                LASTLOC(_M=[0 0 1 0]) is [0 0 0 0]. 
                           [0 1 1 0]     [0 0 0 0] 
                           [0 1 0 1]     [0 0 0 1] 
                           [0 0 0 0]     [0 0 0 0] 
        (ii)    The right edge 
                LASTLOC(_M,1) is [0 0 1 0]. 
                                 [0 0 1 0] 
                                 [0 0 0 1] 
                                 [0 0 0 0]"""
    min_args=1
    max_args=2
    name='LASTLOC'
    CCodeName='LastLoc'
    opcode=215

class LBOUND(_toBeCompleted):
    """      F90 Inquiry. 
      
      All the declared lower bounds of an array or a specified 
                lower bound. 
 
      Arguments Optional: DIM. 
        ARRAY   any type array. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar if DIM is present, otherwise, a vector of 
                size n. 
 
      Result. 
        (i)     LBOUND(ARRAY,DIM) is equal to the lower bound 
                for subscript DIM of ARRAY. If no bounds is declared, 
                the result is 0. 
        (ii)    LBOUND(ARRAY) has the j-th component equal to 
                LBOUND(ARRAY,j) for each j, 0 to n-1. 
 
      Examples. LBOUND(_A=SET_RANGE(2:3,7:10,0)) is [2,7] and 
                LBOUND(_A,1) is 7. 
 
      See also  UBOUND for upper bound, SHAPE for number of elements, 
                SIZE for total elements, and E... for signals."""
    min_args=1
    max_args=2
    name='LBOUND'
    opcode=130

class LE(_toBeCompleted):
    """      Logical Elemental. 
      
      Tests for first less than or equal to second. 
      
      Usual Forms       X <= Y, X LE Y. 
      Function Form     LE(X,Y). 
 
      Arguments X and Y must both be numeric or character. 
                Complex numbers are an error. 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if X is less than or equal to Y; otherwise, false. 
                A reserved operand is always false. Character are 
                compared in the processor collating sequence. 
      >>>>>>>>>WARNING, floating point operations may not match an exact 
                calculation for nonterminating binary fractions. You 
                cannot predict that .1+.1<=.2 is true. Integer values 
                may be truncated when matched to floating numbers. 
 
      Example.  2<=2.0 is $TRUE."""
    min_args=2
    max_args=2
    name='LE'
    opcode=216
    syntax='arg0 <= arg1'

class LEN(_toBeCompleted):
    """      F90 Inquiry. 
      
      The length of a character entity or the number of bytes in 
                numeric data (extension). 
 
      Argument. STRING is any type, scalar or array. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
 
      Result..  The number of characters in STRING if it is scalar or in 
                an element of STRING if it is an array. 
 
      Example.  LEN('abcdefghijk') is 11."""
    min_args=1
    max_args=1
    name='LEN'
    opcode=217

class LEN_TRIM(_toBeCompleted):
    """      F90 Character Elemental. 
      
      Length of the character argument without 
                trailing blank or tab characters. 
 
      Argument. STRING must be character. 
 
      Signals.  Same as STRING. 
      Units...  None. 
      Form....  Integer of same shape. 
 
      Result..  The number of characters after any trailing blanks or 
                tabs are removed. If STRING has no nonblanks other than 
                tabs the result is 0. 
 
      Examples. LEN_TRIM(' A B  ') is 4 and LEN_TRIM('   ') is 0."""
    min_args=1
    max_args=1
    name='LEN_TRIM'
    opcode=218

class LGE(_toBeCompleted):
    """      F90 Character Elemental. 
      
      Test whether a string is lexically greater 
                than or equal to another string based on the ASCII 
                collating sequence. 
 
      Arguments STRING_A and STRING_B must be character. 
 
      Signals.  Single signal or smaller data. 
      Units...  None, bad if different. 
      Form....  Logical of compatible shape. 
 
      Result..  If the strings are of unequal length, the comparison is 
                made as if the shorter string were extended on the right 
                with blanks to the length of the longer string. If 
                either string has a character not in the ASCII character 
                set, the result is processor dependent. The result is 
                true if the strings are equal or if STRING_A follows 
                STRING_B in the collating sequence; otherwise, false. 
 
      Example.  LGE('ONE','TWO') is $FALSE."""
    min_args=2
    max_args=2
    name='LGE'
    opcode=219

class LGT(_toBeCompleted):
    """      F90 Character Elemental. 
      
      Test whether a string is lexically greater than 
                another string based on the ASCII collating sequence. 
 
      Arguments STRING_A and STRING_B must be character. 
 
      Signals.  Single signal or smaller data. 
      Units...  None, bad if different. 
      Form....  Logical of compatible shape. 
 
      Result..  If the strings are of unequal length, the comparison is 
                made as if the shorter string were extended on the right 
                with blanks to the length of the longer string. If 
                either string has a character not in the ASCII character 
                set, the result is processor dependent. The result is 
                true if STRING_A follows STRING_B in the collating 
                sequence; otherwise, false. 
 
      Example.  LGT('ONE','TWO') is $FALSE."""
    min_args=2
    max_args=2
    name='LGT'
    opcode=220

class LLE(_toBeCompleted):
    """      F90 Character Elemental. 
      
      Test whether a string is lexically less 
                than or equal to another string based on the ASCII 
                collating sequence. 
 
      Arguments STRING_A and STRING_B must be character. 
 
      Signals.  Single signal or smaller data. 
      Units...  None, bad if different. 
      Form....  Logical of compatible shape. 
 
      Result..  If the strings are of unequal length, the comparison is 
                made as if the shorter string were extended on the right 
                with blanks to the length of the longer string. If 
                either string has a character not in the ASCII character 
                set, the result is processor dependent. The result is 
                true if the strings are equal or if STRING_A follows 
                STRING_B in the collating sequence; otherwise, false. 
 
      Example.  LLE('ONE','TWO') is $TRUE."""
    min_args=2
    max_args=2
    name='LLE'
    opcode=221

class LLT(_toBeCompleted):
    """      F90x Character Elemental. 
      
      Test whether a string is lexically less 
      	than another string based on the ASCII collating sequence. 
 
      Arguments STRING_A and STRING_B must be character. 
 
      Signals.  Single signal or smaller data. 
      Units...  None, bad if different. 
      Form....  Logical of compatible shape. 
 
      Result..  If the strings are of unequal length, the comparison is 
                made as if the shorter string were extended on the right 
                with blanks to the length of the longer string. If 
                either string has a character not in the ASCII character 
                set, the result is processor dependent. The result is 
                true if STRING_A follows STRING_B in the collating 
                sequence; otherwise, false. 
 
      Example.  LLT('ONE','TWO') is $TRUE."""
    min_args=2
    max_args=2
    name='LLT'
    opcode=222

class LOG(_toBeCompleted):
    """      F90 Mathematical Elemental. 
      
      Natural logarithm. 
 
      Argument. X must be real or complex, HC is converted to GC. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to log X (base e). A complex 
                result is the principal value with imaginary part in the 
                range -pi to pi. The imaginary part of the result is pi 
                only when the real part of X is less than zero and the 
                imaginary part of X is zero. 
 
      Example.  LOG(10.0) is 2.302581, approximately."""
    min_args=1
    max_args=1
    name='LOG'
    opcode=223

class LOG10(_toBeCompleted):
    """      F90 Mathematical Elemental. 
      
      Common logarithm. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to log X (base 10). 
 
      Example.  LOG10(10.0) is 1.0 approximately."""
    min_args=1
    max_args=1
    name='LOG10'
    opcode=224

class LOG2(_toBeCompleted):
    """      Mathematical Elemental. 
      
      Logarithm, base 2. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to log X (base 2). 
 
      Example.  LOG2(8.0) is 3.0 approximately."""
    min_args=1
    max_args=1
    name='LOG2'
    opcode=225

class LOGICAL(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to a logical. True is 1BU, False is 0BU. 
 
      Argument. Optional: KIND. 
        A       integer. 
        KIND    scalar integer type number, for example, KIND($TRUE). 
                (Today, there is only one logical type.) 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Logical (byte_unsigned) of same shape. 
 
      Result..  True if lowest bit of converted integer is on. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  LOGICAL(_L OR NOT _L) is $TRUE."""
    min_args=1
    max_args=2
    name='LOGICAL'
    opcode=226

class LONG(_toBeCompleted):
    """      Conversion Elemental. Convert to long (four-byte) integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Long-length integer of same shape. 
 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. LONG(123.4) is 123."""
    min_args=1
    max_args=1
    name='LONG'
    opcode=227

class LONG_UNSIGNED(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to long (four-byte) unsigned integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Long-length unsigned integer of same shape. 
 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. LONG_UNSIGNED(123) is 123LU. 
                LONG_UNSIGNED(-1) is 4294967295LU."""
    min_args=1
    max_args=1
    name='LONG_UNSIGNED'
    opcode=228

class LT(_toBeCompleted):
    """      Logical Elemental. 
      
      Tests for first less or equal to second. 
      
      Usual Forms       X < Y, X LT Y. 
      Function Form     LT(X,Y). 
 
      Arguments X and Y must both be numeric or character. 
                Complex numbers are an error. 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if X is less than Y; otherwise, false. A reserved 
                operand is always false. Character are compared in the 
                processor collating sequence. 
      >>>>>>>>>WARNING, floating point operations may not match an exact 
                calculation for nonterminating binary fractions. You 
                cannot predict that .1+.1<=.2 is true. Integer values 
                may be truncated when matched to floating numbers. 
 
      Example.  2<2.0 is $FALSE."""
    min_args=2
    max_args=2
    name='LT'
    syntax='arg- < arg1'
    opcode=229

class _MAKE_(_completed):
  """Handle MAKE builtins evaluation by evaluating the args and creating
  and evaluating the BUILD equivalent."""
  def _evaluate(self):
    args=self.evaluateArgs()
    return self.builtins_by_name[self.__class__.__name__.replace('MAKE_','BUILD_')](args)._evaluate()

class MAKE_ACTION(_MAKE_):
    """      MDS Operation. 
      
      Make an action descriptor. 
 
      Arguments 
        DISPATCH dispatch descriptor. 
        TASK    procedure, program, routine, or method descriptor. 
        ERRORLOGS a character scalar for error reports. 
        COMPLETION notification list. 
        PERFORMANCE unsigned long vector of statistics from execution. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  MAKE_ACTION(MAKE_DISPATCH("ident","phase","when", 
                "completion"),MAKE_ROUTINE(timeout,image,routine)) 
                has only dispatch and task."""
    min_args=2
    max_args=5
    name='MAKE_ACTION'
    opcode=418

class MAKE_CALL(_MAKE_):
    """      MDS Operation. 
      
      Make a call of a routine in a sharable image. 
      
      Usual Forms       IMAGE->ROUTINE:KIND([ARG],...) or IMAGE->ROUTINE([ARG]) 
 
      Arguments Optional: KIND, ARG... . 
        KIND    byte unsigned scalar of KIND returned in R0. 
                Use DSC$K_DTYPE_DSC=24 for a pointer to an XD. 
                Use DSC$K_DTYPE_MISSING=0 for no information. 
                Default type is long integer. 
                Other accepted types are BU WU LU QU OU B W L Q O F D 
                NID and null-terminated strings T PATH EVENT. 
        IMAGE   character scalar. It must be a simple filename in 
                SYS$SHARE or a logical name of the file. 
        ROUTINE character scalar. 
        ARG...  arguments with certain options. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
                Use this form if IMAGE or ROUTINE must be expressions. 
 
      Example.  MAKE_CALL(24,'TDISHR','TDI$SIND',DESCR(30.)) is 
                the slow and hard way to do SIND(30.). 
 
      See also. CALL for info on argument form and type of output."""
    min_args=3
    max_args=254
    name='MAKE_CALL'
    opcode=434

class MAKE_CONDITION(_MAKE_):
    """      MDS Operation. 
      
      Make a condition descriptor. 
 
      Arguments 
        MODIFIER word unsigned, evaluated: 
                TREE$K_NEGATE_CONDITION 7 
                TREE$K_IGNORE_UNDEFINED 8 
                TREE$K_IGNORE_STATUS    9 
        CONDITION MDS event or path. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by COMPILE_DEPENDENCY. 
 
      See also. MAKE_DEPENDENCY MAKE_EVENT and COMPILE_DEPENDENCY."""
    min_args=2
    max_args=2
    name='MAKE_CONDITION'
    opcode=419

class MAKE_CONGLOM(_MAKE_):
    """      MDS Operation. 
      
      Make a conglomerate descriptor. 
 
      Arguments 
        IMAGE   character scalar. 
        MODEL   character scalar. 
        NAME    character scalar. 
        QUALIFIERS long vector, module dependent. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by module add routines."""
    min_args=4
    max_args=4
    name='MAKE_CONGLOM'
    opcode=420

class MAKE_DEPENDENCY(_MAKE_):
    """      MDS Operation. Make a dependency descriptor. 
 
      Arguments 
        OP_CODE word unsigned scalar, evaluated. 
                TREE$K_DEPENDENCY_AND   10 
                TREE$K_DEPENDENCY_OR    11 
        ARG_1   MDS condition, event, or path. 
        ARG_2   MDS condition, event, or path. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by COMPILE_DEPENDENCY. 
 
      See also. MAKE_CONDITION MAKE_EVENT and COMPILE_DEPENDENCY."""
    min_args=3
    max_args=3
    name='MAKE_DEPENDENCY'
    opcode=421

class MAKE_DIM(_MAKE_):
    """      MDS Operation. 
      
      Make a dimension descriptor. 
 
      Arguments Optional: WINDOW. 
        WINDOW  window descriptor. 
                If missing, all point of AXIS are included and 
                the initial point of the axis has an index of 0. 
        AXIS    slope or, if defined, other descriptor type. 
 
      Signals.  None. 
      Units...  From AXIS. Should be same as WINDOW's value_at_idx0. 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
                The array will have bounds only if the 
                window has a defined value at index 0. 
 
      Example.  MAKE_DIM(MAKE_WINDOW(-1,3,10.),MAKE_SLOPE(3.)) 
                makes dimension with value 
                SET_RANGE(-1..3, [7.,10.,13.,16.,19.])."""
    min_args=2
    max_args=2
    name='MAKE_DIM'
    opcode=422

class MAKE_DISPATCH(_MAKE_):
    """      MDS Operation. 
      
      Make a dispatch descriptor. 
 
      Arguments 
        TYPE    byte unsigned scalar, evaluated: 
                TREE$K_SCHED_ASYNC      1 
                TREE$K_SCHED_SEQ        2 
                TREE$K_SCHED_COND       3 
        IDENT   character scalar. 
        PHASE   character scalar. 
        WHEN    character scalar? 
        COMPLETION character scalar? 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by module add routine."""
    min_args=5
    max_args=5
    name='MAKE_DISPATCH'
    opcode=423

class MAKE_FUNCTION(_MAKE_):
    """      MDS Operation. 
      
      Make a function descriptor. 
 
      Arguments Optional: ARG,... . 
        OPCODE  unsigned word from 0 to the number defined less one. 
        ARG,... as needed by the function described by OPCODE. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  MAKE_FUNCTION(BUILTIN_OPCODE('SIN'),30) makes an 
                expression SIN(30)."""
    min_args=1
    max_args=254
    name='MAKE_FUNCTION'
    opcode=424


class MAKE_METHOD(_MAKE_):
    """      MDS Operation. 
      
      Make a method descriptor. 
 
      Arguments Optional: ARG,... . 
        TIME_OUT real scalar. 
        METHOD  character scalar. 
        OBJECT  character scalar. 
        ARG,... as needed by METHOD applied to OBJECT. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by module add routine."""
    min_args=3
    max_args=254
    name='MAKE_METHOD'
    opcode=425

class MAKE_OPAQUE(_MAKE_):
    """      MDS Operation. 
      
      Construct an Opaque object consisting of a byte array and a description string.
      Usual Forms       BUILD_OPAQUE(ARRAY,STRING)

      Arguments:
        ARRAY   byte unsigned array
        STRING  text to indicate the format of the array (i.e. mpeg,gif,jpeg)

      Result..  Class-R descriptor.
                Use BUILD_xxx for immediate structure building.
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables.

      Example.  BUILD_OPAQUE([32bu,40bu,41bu,...],'jpeg')
                Store a jpeg image in an MDSplus node. The MDSplus python
                module provides an image method for Opaque objects which
                uses the Image python module to examine the bytes
                and determine the Image type contained in the bytes.

                A series of Opaque objects can be stored as individual
                segments in a tree node."""
    min_args=2
    max_args=2
    name='MAKE_OPAQUE'
    opcode=455

class MAKE_PARAM(_MAKE_):
    """      MDS Operation. 
      
      Make a parameter descriptor. 
 
      Arguments 
        VALUE   any. 
        HELP    character. Textual information about VALUE. 
        VALIDATION logical scalar. $VALUE may be used by VALIDATION to 
                test VALUE without explicit reference to a tree path. 
                $THIS will give the parameter descriptor itself. 
                $VALUE and $THIS may only be used within GET_DATA 
                evaluations of the arguments. 
      >>>>>>>>>WARNING Use of $THIS and $VALUE may be infinitely recursive. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
      Example.  MAKE_PARAM(42.0,'The answer.', 
                $VALUE > 6 && HELP_OF($THIS) <> ""). 
                DATA(above) is 42.0 and VALIDATION(above) is 1BU. """
    min_args=3
    max_args=3
    name='MAKE_PARAM'
    opcode=426

class MAKE_PROCEDURE(_MAKE_):
    """      MDS Operation. 
      
      Make a procedure call 
 
      Arguments Optional: ARG,... . 
        TIME_OUT real scalar. 
        LANGUAGE character scalar. The language in which the procedure 
                is written. 
        PROCEDURE character scalar. 
        ARG,... as needed by the procedure. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  None, normally done by module add routine."""
    min_args=3
    max_args=254
    name='MAKE_PROCEDURE'
    opcode=427

class MAKE_PROGRAM(_MAKE_):
    """      MDS Operation. 
      
      Make a program call 
 
      Arguments 
        TIME_OUT real scalar. 
        PROGRAM character scalar. The name of a program to be run. 
                The program must be responsible for entering its data in 
                the tree. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  MAKE_PROGRAM(1.2,'MYDISK:MYPROGRAM'). """
    min_args=2
    max_args=2
    name='MAKE_PROGRAM'
    opcode=428

class MAKE_RANGE(_MAKE_):
    """      MDS Operation. 
      
      Make a range descriptor. 
      
      Usual Form        START .. END [.. DELTA] or START : END [: DELTA]. 

      Arguments Optional: DELTA; START and END when used as subscript 
                limits. See the specific routine; otherwise, required. 
        START   scalar. The starting value. 
        END     scalar. The last value. 
        DELTA   scalar. The increment. Default is one. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
                This uses a data type RANGE, whereas 
                DTYPE_RANGE(START,END,DELTA) is a function. 
                On evaluation, the compatible data type. 
                A vector of length max((END - BEGIN)/DELTA,0) elements. 
 
                The first value will be BEGIN and successive values will 
                differ by DELTA. The last value will not be futher from 
                BEGIN than END. 
      >>>>>>>>>WARNING, the number of element cannot always be predicted 
                for fractional delta, 1:2:.1 may have 10 or 11 elements. 
      >>>>>>>>>WARNINGS, the colon (:) form may be confused with a tree member 
                and the dot-dot (..) form is hard to read/understand, 
                use spaces. 
 
      Examples. 2..5 becomes [2,3,4,5] and 2:5:1.8 becomes [2.,3.8]."""
    min_args=2
    max_args=3
    name='MAKE_RANGE'
    opcode=429

class MAKE_ROUTINE(_MAKE_):
    """      MDS Operation. 
      
      Make a routine descriptor. 
 
      Arguments Optional: ARG,... . 
        TIME_OUT real scalar. 
        IMAGE   character scalar. 
        ROUTINE character scalar. 
        ARG,... as needed by the routine. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  MAKE_ROUTINE(1.2,MYIMAGE,MYROUTINE,5)."""
    min_args=3
    max_args=254
    name='MAKE_ROUTINE'
    opcode=430

class MAKE_SIGNAL(_MAKE_):
    """      MDS Operation. 
      
      Make data with dimensions. 

      Arguments Optional: DIMENSION,... . 
        DATA    any expression. It may include $VALUE for RAW without a 
                tree reference or $THIS to refer to the whole signal. 
                $VALUE and $THIS may only be used within GET_DATA 
                evaluations of the signal. 
      >>>>>>>>>WARNING Use of $THIS and $VALUE may be infinitely recursive. 
        RAW     any expression. Usually the actual stored integer data. 
        DIMENSION,... dimension descriptor. The number of dimension 
                descriptors must match rank of DATA. 
      >>>>>>>>>WARNING, if the dimension is not of data type dimension, then 
                subscripting is by index value and not axis value. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.
                MAKE_SIGNAL(  MAKE_WITH_UNITS( $VALUE*6, 'm/s^2' ), 
                              MAKE_WITH_UNITS( 5./1024*[1,2,3], 'V' ),
                              MAKE_DIMENSION( MAKE_WINDOW( 0,2,10. ),
                                              MAKE_SLOPE( MAKE_WITH_UNITS(3.,'s') )
                            )
             )
             Here the RAW part of the Signal is referred to in the expression for the DATA part as $VALUE.
             NOTE: Use BUILD_xxx for immediate structure building. (From Build_Call.)
             Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables."""
    min_args=2
    max_args=10
    name='MAKE_SIGNAL'
    opcode=431

class MAKE_SLOPE(_MAKE_):
    """      MDS Operation. 
      
      Make a piece-wise linear slope-axis for dimension. 
      >>>>>>>>>WARNING, this is a deprecated feature and there is no assurance 
                of future support. 

      Arguments Optional: BEGIN, END, and more segments. 
        SLOPE   real scalar. Ratio of change of axis to change of index. 
        BEGIN   real scalar. Axis starting point. 
        END     real scalar. Axis ending point, the last value. 
 
                Note. The axis may be divided into multiple segments. 
                Without a window ISTART, there must be a first BEGIN. 
                If the slope is used in a dimension with a window,  then 
                the greater of the window's ISTART or the first BEGIN is 
                used and the lesser of the window's IEND or the last END 
                is used, assuming positive slope. 
 
      Signals.  None. 
      Units...  Combined from SLOPE and BEGIN. END units are combined 
                from the first segment if no BEGIN is applied. 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Examples. MAKE_SLOPE(3.0) is a constant ratio of 3 axis values 
                per index step. Axes can be infinite in extent. 
                A finite axis of MAKE_SLOPE(3,12,21) has data points 
                [12,15,18,21]. 
                MAKE_SLOPE(3.0,,10.,4.0,20.0) has points at 
                ...,4.0,7.0,20.0,24.0,28.0,... . Note that the dead zone 
                from 10 to 20 is absent and that thus 10.0 becomes 20.0. 
                Often BEGIN[j+1] is the same as END[j] + SLOPE[j] as in 
                a clock that does not stop but does change rate."""
    min_args=1
    max_args=254
    name='MAKE_SLOPE'
    opcode=440

class MAKE_WINDOW(_MAKE_):
    """      MDS Operation. 
      
      Make a window descriptor for a dimension. 

      Arguments Optional: ISTART, IEND, X_AT_0. 
        ISTART  integer scalar. First element stored. 
        IEND    integer scalar. Last element stored. 
        X_AT_0  real scalar. Value at index zero. 
                The effective defaults are -HUGE(1), +HUGE(1), and zero. 
                If missing completely, the beginning of the axis is 
                used for X_AT_0 when evaluating a dimension. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  MAKE_WINDOW(-1024,7168,MAKE_WITH_UNIT(-0.1,'s'))"""
    min_args=3
    max_args=3
    name='MAKE_WINDOW'
    opcode=432

class MAKE_WITH_ERROR(_MAKE_):
    """      MDS Operation.
      
      Make a data with error structure. 
 
      Arguments 
        DATA    any expression that DATA(this) will be valid. 
        ERROR   Error value. 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example:

          _A0 = Build_With_Error(52.9177E-12, 2400E-21)"""
    min_args=2
    max_args=2
    name='MAKE_WITH_ERROR'
    opcode=447

class MAKE_WITH_UNITS(_MAKE_):
    """      MDS Operation. 
      
      Make a describe data with units. 
      
      Arguments 
        DATA    any expression that DATA(this) will be valid. 
        UNITS   character string. See the primary section on "Units". 
 
      Result..  Class-R descriptor. 
                Use BUILD_xxx for immediate structure building. 
                Use MAKE_xxx in FUNs for evaluated non-PUBLIC variables. 
 
      Example.  _S = MAKE_WITH_UNITS($VALUE*6,'m/s^2') can be used in a 
                MAKE_SIGNAL(_S,MAKE_WITH_UNITS(5./1024*raw_node,'V') 
                or similar. Note this could also have been 
                MAKE_WITH_UNITS(MAKE_SIGNAL($VALUE*6, 
                MAKE_WITH_UNITS(5./1024*raw_node,'V')),'m/s^2')."""
    min_args=2
    max_args=2
    name='MAKE_WITH_UNITS'
    opcode=433

class MAP(_toBeCompleted):
    """      Transformation. 
      
      Element selection from an array. 
 
      Arguments 
        A       an array of any type considered to be a vector. 
        B       a list of offsets into the A array. 
                Values are from 0 to the number of elements in A less 1. 
                Out-of-bounds values are considered to be at the limits. 
 
      Signals.  Same as B. 
      Units...  Same as A. 
      Form....  Same type as A and same shape as B. 
 
      Result..  Each value in B is used to look up a value in A. 
                The value is copied into the result. 
                This is the same as A(B) in IDL when B is a vector. 
      >>>>>>>>>WARNING, multidimensional arrays referenced by bad offsets 
                will likely be junk. 
 
      Examples. MAP(1..10,[20,-1,5]) is [10,1,6]. 
                _A=5..1..-1, MAP(_A,SORTI(_A)) is [1,2,3,4,5], 
                which is the same as SORT(5..1..-1). 
 
      See also. CULL to remove bad B values. 
                SUBSCRIPT for dimensional indexing into signal and 
                multiple index access to arrays."""
    min_args=2
    max_args=2
    name='MAP'
    opcode=394

class MAX(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      Maximum value. 
 
      Arguments Integer or real. Complex numbers are an error. 
 
      Signals.  The single signal or the smallest. 
      Units...  The single or matching units, else bad. 
      Form....  The compatible form of all the arguments. Conversion is 
                done pairwise. 
 
      Result..  The largest argument. A reserved operand will dominate. 
 
      Example.  MAX(-9.0,7.0,2.0) is 7.0."""
    min_args=2
    max_args=254
    name='MAX'
    opcode=233

class MAXEXPONENT(_toBeCompleted):
    """      F90 Inquiry. 
      
      The maximum exponent in the model representing numbers of 
                the same type as the argument. 
 
      Argument. X is real, scalar or array. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
 
      Result..  The number emax for the model of the same type as X. 
      Example.  MAXEXPONENT(1.0) is 127 on the VAX."""
    min_args=1
    max_args=1
    name='MAXEXPONENT'
    CCodeName='MaxExponent'
    opcode=234

class MAXLOC(_toBeCompleted):
    """      F90 Transformation. 
      
      Determine the location of an element of ARRAY with 
                the maximum value of the elements identified by MASK. 
 
      Arguments Optional: MASK. 
        ARRAY   numeric array. 
        MASK    logical and conformable with ARRAY. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Long vector of size equal to rank of ARRAY. 
 
      Result..  The result is the vector of subscripts of an element 
                whose value equals the maximum of all elements of ARRAY 
                or all elements for which MASK is true. Reserved 
                operands ($ROPRAND) are ignored. Each subscript will 
                be in the extent of its dimension. For zero size, no 
                true elements in MASK, or all $ROPRAND the result is 
                undefined. If more than one element has the maximum 
                value the result is the first in array order. The result 
                is an offset vector even if there is a lower bound. 
 
      Examples. MAXLOC([2,4,6]) is [2]. 
                For _A=[0 -5  8 -3], MAXLOC(_A,_A LT 6) is [2,1]. 
                       [3  4 -1  2] 
                       [1  5  6 -4] 
 
      See also. MAXVAL for the value."""
    min_args=1
    max_args=3
    name='MAXLOC'
    CCodeName='MaxLoc'
    opcode=235

class MAXVAL(_toBeCompleted):
    """      F90 Transformation. 
      
      Maximum value of the elements of ARRAY along 
                dimension DIM corresponding to true elements of MASK. 
 
      Arguments Optional: DIM, MASK. 
        ARRAY   numeric array. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
        MASK    logical and conformable to ARRAY. 
 
      Signals.  Same as ARRAY if DIM-th or all dimensions omitted. 
      Units...  Same as ARRAY. 
      Form....  Same type as ARRAY. It is a scalar if DIM is absent or 
                ARRAY is scalar or vector. Otherwise, the result is an 
                array of rank n-1 and shaped like ARRAY with DIM 
                subscript omitted. 
 
      Result..  The result without DIM is the maximum value of the 
                elements of ARRAY, testing only those with true MASK 
                values and value not equal to the reserved operand 
                ($ROPRAND). With DIM, the value of an element of the 
                result is the maximum of ARRAY elements with DIM 
                dimension fixed as the element number of the result. 
                If no value is found, -HUGE(ARRAY) is returned. 
 
      Examples. MAXVAL([1,2,3]) is 3. MAXVAL(_C,,_C LT 0) finds the 
                maximum negative element of C. If 
                _B=[[1, 3, 5],[2, 4, 6]]
                MAXVAL(_B,0) is [5,6] and MAXVAL(_B,1) is [2,4,6]. 
 
      See also. MAXLOC for the location."""
    min_args=1
    max_args=3
    name='MAXVAL'
    CCodeName='MaxVal'
    opcode=236

class MEAN(_toBeCompleted):
    """      Transformation. 
      
      Average value of the elements of ARRAY along dimension 
                DIM corresponding to the true elements of MASK. 
 
      Arguments Optional: DIM, MASK. 
        ARRAY   numeric array. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
        MASK    logical and conformable to ARRAY. 
 
      Signals.  Same as ARRAY if DIM-th or all dimensions omitted. 
      Units...  Same as ARRAY. 
      Form....  Same type as ARRAY. It is a scalar if DIM is absent or 
                ARRAY is scalar or vector. Otherwise, the result is an 
                array of rank n-1 and shaped like ARRAY with DIM 
                subscript omitted. 
 
      Result..  The result without DIM is the mean value of the elements 
                of ARRAY, testing only those with true MASK values and 
                value not equal to the reserved operand ($ROPRAND). With 
                DIM, the value of an element of the result is the mean 
                of ARRAY elements with dimension DIM fixed as the 
                element number of the result. 
                If no value is found, zero is given. 
 
      Examples. MEAN([1,2,3]) is 2. MEAN(_C,,_C GT 0) finds the mean of 
                positive element of C.
		If :
                _B=[[1, 3, 5],[2, 4, 6]]
                MEAN(_B,0) is [3,4] and MEAN(_B,1) is [1,3,5]."""
    min_args=1
    max_args=3
    name='MEAN'
    opcode=237

class MERGE(_toBeCompleted):
    """      F90 Logical Elemental. 
      
      Choose alternative value according to a mask. 
 
      Arguments 
        TSOURCE any type compatible with FSOURCE. 
        FSOURCE any type compatible with TSOURCE. 
        MASK    logical, conformable with TSOURCE and FSOURCE. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units (excluding MASK), else bad. 
      Form....  The type is the compatible type of FSOURCE and TSOURCE. 
                The shape conformable to FSOURCE, TSOURCE, and MASK. 
 
      Result..  If the MASK value is true, the TSOURCE value is use; 
                otherwise, the FSOURCE value is use. 
 
      Examples. MERGE([1,2,3],[4,5,6],[$TRUE,$FALSE,$TRUE]) is [1,5,3]. 
                If TSOURCE is the array [1 6 5], FSOURCE is the array 
                                        [2 4 6] 
                [0 3 2] and MASK is [1 0 1], 
                [7 4 8]             [0 0 1] 
                then MERGE(TSOURCE,FSOURCE,MASK) 
                is [1 3 5]. 
                   [7 4 6] 
 
      See also. CONDITIONAL with form: MASK ? TSOURCE : FSOURCE, for 
                scalar mask test."""
    min_args=3
    max_args=3
    name='MERGE'
    opcode=239

class METHOD_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the method field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_METHOD, the method field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='METHOD_OF'
    opcode=240

class MIN(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      Minimum value. 
 
      Arguments Integer or real. Complex numbers are an error. 
 
      Signals.  The single signal or the smallest. 
      Units...  The single or matching units, else bad. 
      Form....  The compatible form of all the arguments. Conversion is 
                done pairwise. 
 
      Result..  The smallest argument. A reserved operand will dominate. 
 
      Example.  MIN(-9.0,7.0,2.0) is -9.0."""
    min_args=2
    max_args=254
    name='MIN'
    opcode=241

class MINEXPONENT(_toBeCompleted):
    """      F90 Inquiry. 
      
      The minimum exponent in the model representing numbers of 
                the same type as the argument. 
 
      Argument. X must be real or complex, scalar or array. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
 
      Result..  The number emin for the model of the same type as X. 
 
      Example.  MINEXPONENT(1.0) is -127 on the VAX."""
    min_args=1
    max_args=1
    name='MINEXPONENT'
    CCodeName='MinExponent'
    opcode=242

class MINLOC(_toBeCompleted):
    """      F90 Transformation. 
      
      Determine the location of an element of ARRAY 
      	having the minimum value of the elements identified by MASK. 
 
      Arguments Optional: MASK. 
        ARRAY   numeric array. 
        MASK    logical and conformable with ARRAY. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Long vector of size equal to rank of ARRAY. 
 
      Result..  The result is the vector of subscripts of an element 
                whose value equals the minimum of all elements of ARRAY 
                or all elements for which MASK is true. Reserved 
                operands ($ROPRAND) are ignored. Each subscript will 
                be in the extent of its dimension. For zero size, no 
                true elements in MASK, or all $ROPRAND the result is 
                undefined. If more than one element has the maximum 
                value the result is the first in array order. The result 
                is an offset vector even if there is a lower bound. 
 
      Examples. MINLOC([2,4,6]) is [0]. 
                For _A=[0 -5  8 -3], MINLOC(_A,_A GT -4) is [0,3]. 
                       [3  4 -1  2] 
                       [1  5  6 -4] 
 
      See also. MINVAL for the value."""
    min_args=1
    max_args=3
    name='MINLOC'
    CCodeName='MinLoc'
    opcode=243

class MINVAL(_toBeCompleted):
    """      F90 Transformation. 
      
      Minimum value of the elements of ARRAY along 
                dimension DIM corresponding to true elements of MASK. 
 
      Arguments Optional: DIM, MASK. 
        ARRAY   numeric array. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
        MASK    logical and conformable to ARRAY. 
 
      Signals.  Same as ARRAY if DIM-th or all dimensions omitted. 
      Units...  Same as ARRAY. 
      Form....  Same type as ARRAY. It is a scalar if DIM is absent or 
                ARRAY is scalar or vector. Otherwise, the result is an 
                array of rank n-1 and shaped like ARRAY with DIM 
                subscript omitted. 
      Result..  The result without DIM is the minimum value of the 
                elements of ARRAY, testing only those with true MASK 
                values and value not equal to the reserved operand 
                ($ROPRAND). With DIM, the value of an element of the 
                result is the minimum of ARRAY elements with DIM 
                dimension fixed as the element number of the result. 
                If no value is found, +HUGE(ARRAY) is returned. 
 
      Examples. MINVAL([1,2,3]) is 3. MINVAL(_C,,_C GT 0) finds the 
                minimum positive element of C. 
                If 
		_B=[[1, 3, 5],[2, 4, 6]]
                MINVAL(_B,0) is [1,2] and MINVAL(_B,1) is [1,3,5]. 
 
      See also. MINLOC for the location."""
    min_args=1
    max_args=3
    name='MINVAL'
    CCodeName='MinVal'
    opcode=244

class MOD(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      Remainder. 
      
      Usual Form        A MOD P. 
 
      Arguments A and P must be integer or real. 
                Complex numbers are an error. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Compatible form of A and P. 
 
      Result..  If P NE 0, the result is A-INT(A/P)*P. If P==0, the result 
                is the $ROPRAND for reals and undefined for integers. 
 
      Examples. MOD(3.0,2.0) is 1.0. MOD(8,5) is 3. MOD(-8,5) is -3. 
                MOD(8,-5) is -3. MOD(-8,-5) is -3."""
    min_args=2
    max_args=2
    name='MOD'
    syntax='arg0 MOD arg1'
    opcode=245

class MODEL_OF(_PART_OF):
    """      MDS Operation. Get the model field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_CONGLOM, the model field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='MODEL_OF'
    opcode=246

class MULTIPLY(_toBeCompleted):
    """      Numeric Elemental. 
      
      Multiplication. 
      
      Usual Form        X * Y. 
      Function Form     MULTIPLY(X,Y). 
 
      Arguments X and Y must be numeric. 
 
      Signals.  Single signal or smaller data. 
      Units...  Those of X joined with those of Y by an asterisk. 
      Form....  Compatible form of X and Y. 
 
      Result..  Product of corresponding elements of X and Y. 
      >>>>>>>>>WARNING, integer overflow is ignored. 
 
      Examples. 3.0 * 2 is 6.0. BUILD_WITH_UNITS(3.0,"V") 
                * BUILD_SIGNAL(BUILD_WITH_UNITS($VALUE*2,"s"),4)) is 
                BUILD_SIGNAL(BUILD_WITH_UNITS(24.0,"V*s"),4)."""
    min_args=2
    max_args=2
    name='MULTIPLY'
    syntax='arg0 * arg1'
    opcode=247

class NAME_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the name field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_CONGLOM, the name field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='NAME_OF'
    opcode=248

class NAND(_toBeCompleted):
    """      Logical Elemental. 
      
      Negation of logical intersection of elements. 
      
      Usual Forms       L NAND M. 
 
      Arguments L and M must be logical (lowest bit is 1 for true). 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  False if both are true; otherwise, true. 
 
      Example.  [0,0,1,1] && [0,1,0,1] is [$TRUE,$TRUE,$TRUE,$FALSE]."""
    min_args=2
    max_args=2
    name='NAND'
    opcode=249

class NAND_NOT(_toBeCompleted):
    """      Logical Elemental. 
      
      Negation of logical intersection of first with 
                negation of second. Logically equivalent to NOT(L) OR M. 
      
      Accepted Form. L NAND_NOT M. 
 
      Arguments L and M must be logical (lowest bit is 1 for true). 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if L is false or M is true; otherwise, false. 
      Example.  [0,0,1,1] NAND_NOT [0,1,0,1] is 
                [$TRUE,$TRUE,$FALSE,$TRUE]."""
    min_args=2
    max_args=2
    name='NAND_NOT'
    opcode=250

class NDESC(_toBeCompleted):
    """      MDS Information. 
      
      The number of descriptors in an MDS record. 
 
      Argument. A must be an MDS class-R descriptor. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Byte unsigned scalar. 
      Result..  The number of descriptors in the class-R descriptor. 
                Descriptor data types (DSC$K_DTYPE_DSC) are removed. 
                Use NDESC for count without NID, PATH, or variable. 
                Use NDESC_OF for count including them. 
 
      Examples. NDESC($VALUE) is 0. NDESC(A+B) may be error."""
    min_args=1
    max_args=1
    name='NDESC'
    opcode=251

class NDESC_OF(_toBeCompleted):
    """      MDS Information. 
      
      The number of descriptors in an MDS record. 
 
      Argument. A must be an MDS class-R descriptor. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Byte unsigned scalar. 
 
      Result..  The number of descriptors in the class-R descriptor. 
                Descriptor data types (DSC$K_DTYPE_DSC) are removed. 
                Use NDESC for count without NID, PATH, or variable. 
                Use NDESC_OF for count including them. 
 
      Examples. NDESC_OF($VALUE) is 0. NDESC_OF(A+B) is 2."""
    min_args=1
    max_args=1
    name='NDESC_OF'
    opcode=438

class NE(_toBeCompleted):
    """      Logical Elemental. 
      
      Tests for inequality of two values. 
      
      Usual Forms       X != Y, X <> Y, X NE Y. F90 form /= is not allowed. 
      Function Form     NE(X,Y). 
 
      Arguments X and Y must both be numeric or character. 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if X and Y are the unequal; otherwise, false. 
                $ROPRAND is not unequal to any value, thus gives false. 
      >>>>>>>>>WARNING, floating point operations may not match an exact 
                calculation for nonterminating binary fractions. 
                You cannot predict that .1+.1!=.2 will be false. 
 
      Example.  2<>2. is $FALSE."""
    min_args=2
    max_args=2
    name='NE'
    syntax='arg0 != arg1, arg0 <> arg1, arg0 NE arg1'
    opcode=252

class NEQV(_toBeCompleted):
    """      Logical Elemental. 
      
      Test that logical values are unequal. 
 
      Arguments L and M must be logical (lowest bit is 1 for true). 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
      Result..  True if exactly one of X and Y are true; 
                otherwise, false. 
 
      Example.  2>3 NEQV 3>4 is $FALSE."""
    min_args=2
    max_args=2
    name='NEQV'
    opcode=254

class NINT(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      Nearest integer. 
 
      Argument. Optional: KIND. 
        A       real. Complex numbers are an error. 
                Integers are passed. 
        KIND    scalar integer type number, for example, KIND(1). 
                (Today. Ignored, always returns LONG.) 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Integer. 
 
      Result..  If A>0, NINT(A) is INT(A+0.5); else it is INT(A-0.5). 
 
      Examples. NINT(2.783) is 3. NINT(-2.783) is -3."""
    min_args=1
    max_args=2
    name='NINT'
    opcode=255

class NOR(_toBeCompleted):
    """      Logical Elemental. 
      
      Negation of logical union of elements. 
      
      Usual Forms       L NOR M. 
 
      Arguments L and M must be logical (lowest bit is 1 for true). 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  False if either is true; otherwise, true. 
 
      Example.  [0,0,1,1] && [0,1,0,1] is [$TRUE,$FALSE,$FALSE,$FALSE]."""
    min_args=2
    max_args=2
    name='NOR'
    opcode=256

class NOR_NOT(_toBeCompleted):
    """      Logical Elemental. 
      
      Negation of logical union of first with negation 
                of second. Logically equivalent to NOT(L) AND M. 
      
      Accepted Form. L NOR_NOT M. 
 
      Arguments L and M must be logical (lowest bit is 1 for true). 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if L is false and M is true; otherwise, false. 
 
      Example.  [0,0,1,1] NOR_NOT [0,1,0,1] is 
                [$FALSE,$TRUE,$FALSE,$FALSE]."""
    min_args=2
    max_args=2
    name='NOR_NOT'
    opcode=257

class NOT(_toBeCompleted):
    """      Logical Elemental. 
      
      Negate a logical. True is 1BU, False is 0BU. 
      
      Usual Form        ! L or NOT L. 
      Function Form     NOT(L). 
 
      Argument. L must be logical. 
 
      Signals.  Same as L. 
      Units...  Same as L. 
      Form....  Logical. 
 
      Result..  True if lowest bit of converted integer is off. 
      >>>>>>>>>WARNING, do not confuse this with the bit-wise INOT(J). 
                What F90 calls NOT, we call INOT. 
 
      Example.  NOT([1,2,3]) is [$FALSE,$TRUE,$FALSE])."""
    min_args=1
    max_args=1
    name='NOT'
    opcode=258

class OBJECT_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the object field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_METHOD, the object field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='OBJECT_OF'
    opcode=259

class OCTAWORD(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to octaword (16-byte) integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Octaword-length integer. 
 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. OCTAWORD(123) is 123O. OCTAWORD(65537) is 65537O."""
    min_args=1
    max_args=1
    name='OCTAWORD'
    opcode=260

class OCTAWORD_UNSIGNED(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to octaword (16-byte) unsigned integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Octaword-length unsigned integer. 
 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
      Example.  OCTAWORD_UNSIGNED(123) is 123oU."""
    min_args=1
    max_args=1
    name='OCTAWORD_UNSIGNED'
    opcode=261

class OPCODE_BUILTIN(_completed):
    """      MDS Information. 
      
      The string name of a builtin's opcode. 
 
      Argument. I must be an unsigned word scalar. It must be from 0 to 
                the number of defined opcodes less one. 
 
      Signals.  Same as I. 
      Units...  Same as I. 
      Form....  Character scalar of same shape. 
      Result..  The uppercase name for the opcode. 
 
      Example.  OPCODE_BUILTIN(0) is "$"."""
    min_args=1
    max_args=1
    name='OPCODE_BUILTIN'
    opcode=263
    def _evaluate(self):
      return _data.String(self.builtins_by_opcode[int(self.args[0])].name)

class OPCODE_STRING(_completed):
    """      MDS Information. 
      
      The string name of an opcode. 
 
      Argument. I must be an unsigned word scalar. It must be from 0 to 
                the number of defined opcodes less one. 
 
      Signals.  Same as I. 
      Units...  Same as I. 
      Form....  Character scalar of same shape. 
 
      Result..  The uppercase name for the opcode. 
 
      Example.  OPCODE_STRING(0) is "OPC$$"."""
    min_args=1
    max_args=1
    name='OPCODE_STRING'
    opcode=264
    def _evaluate(self):
      return _data.String('OPC$'+str(OPCODE_BUILTIN(*self.args)._evaluate()))

class OPTIONAL(_toBeCompleted):
    """Used in FUN definitions to indicate argument is optional"""
    min_args=1
    max_args=1
    name='OPTIONAL'
    syntax='OPTIONAL _arg'
    opcode=266

class OR(_completed):
    """      Logical Elemental. 
      
      Logical union of elements. 
      
      Usual Forms       L || M, L OR M. 
      Function Form     OR(L,M). 
 
      Arguments L and M must be logical (lowest bit is 1 for true). 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if either is true; otherwise, false. 
      >>>>>>>>>WARNING, do not confuse with | which is bit-wise IOR. 
 
      Example.  [0,0,1,1] || [0,1,0,1] is [$FALSE,$TRUE,$TRUE,$TRUE]."""
    min_args=2
    max_args=2
    name='OR'
    syntax='arg0 || arg1, arg0 OR arg1'
    opcode=267
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        ans=((_NP.uint8(dargs[0])&1)+(_NP.uint8(dargs[1])&1)) > 0
        if isinstance(args[0],_data.Signal) and not isinstance(args[1],_data.Signal):
            ans=_updateSignal(args[0],ans)
        elif isinstance(args[1],_data.Signal) and not isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[1],ans)
        else:
            ans=self.makeData(ans)
        return ans

class OR_NOT(_completed):
    """      Logical Elemental. 
      
      Logical union of first with negation of second. 
      
      Accepted Form. L OR_NOT M. 
 
      Arguments L and M must be logical (lowest bit is 1 for true). 
 
      Signals.  Single signal or smaller data. 
      Units...  None unless both have units and they don't match. 
      Form....  Logical of compatible shape. 
 
      Result..  True if L is true or M is false; otherwise, false. 
 
      Example.  [0,0,1,1] OR_NOT [0,1,0,1] is [$TRUE,$FALSE,$TRUE,$TRUE]."""
    min_args=2
    max_args=2
    name='OR_NOT'
    opcode=268
    def _evaluate(self):
        args=self.evaluateArgs()
        dargs=_dataArgs(args)
        ans=((_NP.uint8(dargs[0])&1)+(_NP.uint8(_NP.uint8(dargs[1])&1==0))) > 0
        if isinstance(args[0],_data.Signal) and not isinstance(args[1],_data.Signal):
            ans=_updateSignal(args[0],ans)
        elif isinstance(args[1],_data.Signal) and not isinstance(args[0],_data.Signal):
            ans=_updateSignal(args[1],ans)
        else:
            ans=self.makeData(ans)
        return ans

class OUT(_toBeCompleted):
    """Used in FUN definitions to indicate argument is an output argument"""
    min_args=1
    max_args=1
    name='OUT'
    syntax='OUT _arg'
    opcode=269

class PACK(_toBeCompleted):
    """      F90 Transformation. 
      
      Pack an array into a vector under control of a 
      mask. 
 
      Arguments Optional: VECTOR. 
        ARRAY   any type. 
        MASK    logical conformable to ARRAY. 
        VECTOR  ARRAY's type, length at least equal to last true element 
                of MASK. 
 
      Signals.  The single signal or the smallest. 
      Units...  The single or matching units, else bad. 
      Form....  The type is from ARRAY, ARRAY. The shape is rank one 
                equal to the number of trues if no VECTOR or the shape 
                of VECTOR if present. If no VECTOR and MASK is a scalar 
                true, the result is ARRAY shaped. 
 
      Result..  The elements as selected by MASK from ARRAY. The 
                remaining elements are filled from VECTOR. 
 
      Examples. Gather the nonzero elements of M = [0,0,0]. 
                                                   [9,0,0] 
                                                   [0,0,7] 
                PACK(M,M NE 0) is [9,7] and 
                PACK(M,M NE 0,[2,4,6,8,10,12]) is [9,7,6,8,10,12]."""
    min_args=2
    max_args=3
    name='PACK'
    opcode=270

class PERFORMANCE_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the performance field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_ACTION, the performance statistics field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='PERFORMANCE_OF'
    opcode=399

class PHASE_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the phase field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_DISPATCH, the phase field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='PHASE_OF'
    opcode=271

class POST_DEC(_toBeCompleted):
    """      Variable Elemental. 
      
      Decrement variable but give old value. 
      
      Usual Form        NAME--. 
      Function Form     POST_DEC(NAME). 
 
      Argument. NAME must be a variable with numeric value or operator 
                on variable. 
 
      Signals.  Same as NAME. 
      Units...  Same as NAME. 
      Form....  Same as NAME. 
 
      Result..  Old value of NAME. 
 
      Side Effect. NAME is now one less than before. 
 
      Example.  For _A=6, A-- is 6 and _A is now 5."""
    min_args=1
    max_args=1
    name='POST_DEC'
    syntax='_var--'
    opcode=272

class POST_INC(_toBeCompleted):
    """      Variable Elemental. 
      
      Increment variable but give old value. 
      
      Usual Form        NAME++. 
      Function Form     POST_INC(NAME). 
 
      Argument. NAME must be a variable with numeric value or operator 
                on variable. 
 
      Signals.  Same as NAME. 
      Units...  Same as NAME. 
      Form....  Same as NAME. 
 
      Result..  Old value of NAME. 
 
      Side Effect. NAME is now one more than before. 
 
      Example.  For _A=6, A++ is 6 and _A is now 7."""
    min_args=1
    max_args=1
    name='POST_INC'
    syntax='_var++'
    opcode=273

class POWER(_toBeCompleted):
    """      Numeric Elemental. 
      
      Raise number to a power. 
      
      Usual Forms       X^Y, X**Y. 
      Function Form     POWER(X,Y). 
 
      Arguments X and Y must be numeric. 
 
      Signals.  Single signal or smaller data. 
      Units...  None, bad if X or Y have units. 
      Form....  The compatible form of X and Y if both are byte, word, 
                or long or both are real or complex; otherwise, the type 
                of X. 
      >>>>>>>>>WARNING, long unsigned and longer integer types are truncated. 
      >>>>>>>>>WARNING, quad-precision complex--HC^HC is truncated to GC^GC. 
 
      Result..  Converts integer exponents to long and takes integral 
                power. For real, or complex powers gives EXP(LOG(X)*Y). 
                This will be $ROPRAND if X is not positive. 
      >>>>>>>>>WARNING, 0.0^0 is not detected as an error and results in 1.0. 
      >>>>>>>>>WARNING, do not use -X^2., which is (-X)^2.0, when you 
                mean -(X^2), because it will bomb. Note that negation 
                binds tighter than power. 
      >>>>>>>>>WARNING, use integer exponents when you mean that. For 
                example, X^2.0 is an order of magnitude slower than X^2. 
 
      Examples. 2^3 is 8. 2**0.5 is 1.41428, approximately, and is 
                better written as SQRT(2)."""
    min_args=2
    max_args=2
    name='POWER'
    syntax='arg0 ^ arg1, arg0 ** arg1'
    opcode=274

class PRECISION(_toBeCompleted):
    """      Inquiry. 
      
      The decimal precision in the model representing numbers of 
                the argument type. 
 
      Argument. X must be real or complex, scalar or array. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
 
      Result..  INT((p-1)*LOG10(b))+k, where p is the number of fraction 
                digits, b is the digit size, and k is 1 if b is an 
                integral power of ten and 0 otherwise. 
 
      Example.  PRECISION(1.0) is INT((24-1)*LOG10(2))=INT(6.92)=6 
                on the VAX."""
    min_args=1
    max_args=1
    name='PRECISION'
    opcode=142

class PRESENT(_toBeCompleted):
    """      F90 Variable Inquiry. 
      
      Determine if an optional argument present. 
 
      Argument. A must be an optional argument of the FUN in which 
                the PRESENT function reference appears. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Logical scalar. 
 
      Result..  $TRUE if A present or $FALSE otherwise. 
      Example.  FUN _test(_A) {return PRESENT(_A);} when called _test() 
                is $FALSE and _test(3) is $TRUE."""
    min_args=1
    max_args=1
    name='PRESENT'
    opcode=275

class PRE_DEC(_toBeCompleted):
    """      Variable Elemental. 
      
      Decrement variable and give new value. 
      
      Usual Form        --NAME. 
      Function Form     PRE_DEC(NAME). 
 
      Argument. NAME must be a variable with numeric value or operator 
                on variable. 
 
      Signals.  Same as NAME. 
      Units...  Same as NAME. 
      Form....  Same as NAME. 
 
      Result..  New value of NAME. 
 
      Side Effect. NAME is now one less than before. 
 
      Example.  For _A=6, --A is 5 and _A is now 5."""
    min_args=1
    max_args=1
    name='PRE_DEC'
    syntax='--_var'
    opcode=276

class PRE_INC(_toBeCompleted):
    """      Variable Elemental. 
      
      Increment variable and give new value. 
      
      Usual Form        ++NAME. 
      Function Form     PRE_INC(NAME). 
 
      Argument. NAME must be a variable with numeric value or operator 
                on variable. 
 
      Signals.  Same as NAME. 
      Units...  Same as NAME. 
      Form....  Same as NAME. 
 
      Result..  New value of NAME. 
 
      Side Effect. NAME is now one more than before. 
 
      Example.  For _A=6, ++A is 7 and _A is now 7."""
    min_args=1
    max_args=1
    name='PRE_INC'
    syntax='++_var'
    opcode=277

class PRIVATE(_toBeCompleted):
    """      Variable Operation. 
      
      Specifies the use of a private variable. 
      
      Usual Form        PRIVATE NAME. 
 
      Argument. NAME must be a variable name. 
 
      Signals.  None. 
      Units...  None. 
      Form....  A copy of the contents of the variable. 
 
      Result..  That of the contents of the variable. 
 
      Example.  PRIVATE _A = 42 sets the private variable _A to 42."""
    min_args=1
    max_args=1
    name='PRIVATE'
    opcode=278

class PROCEDURE_OF(_PART_OF):
    """      MDS Operation.
      
      Get the procedure field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_PROCEDURE, the procedure field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='PROCEDURE_OF'
    opcode=279

class PRODUCT(_toBeCompleted):
    """      F90 Transformation. 
      
      Product of all the elements of ARRAY along 
                dimension DIM corresponding to true elements of MASK. 
 
      Arguments Optional: DIM, MASK. 
        ARRAY   numeric array. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
        MASK    logical and conformable to ARRAY. 
 
      Signals.  Same as ARRAY if DIM-th or all dimensions omitted. 
      Units...  Those of ARRAY repeated valid number of times. 
                (Today, none.) 
      Form....  Same type as ARRAY. It is a scalar if DIM is absent or 
                ARRAY is scalar or vector. Otherwise, the result is an 
                array of rank n-1 and shaped like ARRAY with DIM 
                subscript omitted. 
      Result. 
        (i)     Without DIM, the product of the elements of ARRAY, using 
                only those with true MASK values and value not equal to 
                the reserved operand. 
        (ii)    With DIM, the value of an element of the result is the 
                product of ARRAY elements with dimension DIM fixed as 
                the element number of the result. If no value is found, 
                the number one is given. 
 
      Examples. 
        (i)     PRODUCT([1,2,3]) is 6. PRODUCT(_C,,_C GT 0) finds the 
                product of all positive element of C. 
        (ii)    If 
	         _B=[[1, 3, 5],[2, 4, 6]]
                PRODUCT(_B,0) is [15,48] and PRODUCT(_B,1) is [2,12,30]."""
    min_args=1
    max_args=3
    name='PRODUCT'
    opcode=280

class PROGRAM_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the program field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_PROGRAM, the program field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='PROGRAM_OF'
    opcode=281

class PUBLIC(_toBeCompleted):
    """      Variable Operation. 
      
      Specifies the use of a public variable. 
      
      Usual Form        PUBLIC NAME. 
 
      Argument. NAME mus be a variable name. 
 
      Signals.  Same as NAME. 
      Units...  Same as NAME. 
      Form....  A copy of the contents of the variable. 
 
      Result..  That of the contents of the variable. 
 
      Example.  PUBLIC _A = 42 sets the public variable _A to 42."""
    min_args=1
    max_args=1
    name='PUBLIC'
    opcode=284

class QUADWORD(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to quadword (8-byte) integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Quadword-length integer. 
 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
      Examples. QUADWORD(123) is 123O. QUADWORD(65537) is 65537O."""
    min_args=1
    max_args=1
    name='QUADWORD'
    opcode=285

class QUADWORD_UNSIGNED(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to quadword (8-byte) unsigned integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Quadword-length unsigned integer. 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  QUADWORD_UNSIGNED(123) is 123oU."""
    min_args=1
    max_args=1
    name='QUADWORD_UNSIGNED'
    opcode=286

class QUALIFIERS_OF(_toBeCompleted):
    """      MDS Operation. 
      
      Get the qualifiers field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_CALL, the type byte unsigned. 
                DSC$K_DTYPE_CONDITION, the modifier unsigned word. 
                DSC$K_DTYPE_CONGLOM, the qualifiers field. 
                DSC$K_DTYPE_DEPENDENCY, the opcode unsigned word. 
                DSC$K_DTYPE_DISPATCH, the type byte unsigned. 
                DSC$K_DTYPE_FUNCTION, the opcode unsigned word. 
                Otherwise, an error. 
 
      Example.  QUALIFIER_OF(A+B) is 38 (at this writing)."""
    min_args=1
    max_args=1
    name='QUALIFIERS_OF'
    opcode=287

class RADIX(_toBeCompleted):
    """      F90 Inquiry. 
      
      The base of the model representing numbers of the 
                same type as the argument. 
 
      Argument. X is numeric scalar or array. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
 
      Result..  The base of the real or integer model. 
 
      Examples. RADIX(1.0) is 2 and RADIX(123) is 2 on the VAX."""
    min_args=1
    max_args=1
    name='RADIX'
    opcode=288

class RAMP(_toBeCompleted):
    """      Transformation. 
      
      Generate an ascending array. 
 
      Arguments Optional: SHAPE, MOLD. 
        SHAPE   integer vector. 
        MOLD    numeric. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Type of MOLD and shape (dimensions) is SHAPE. If SHAPE 
                is absent, the result is a scalar. If MOLD is absent, 
                the result will be longs. 
 
      Result..  Successive integral values starting at zero. 
 
      Example.  _X = RAMP([2,3,4],1d0) makes an array of double 
                precision floating point numbers of shape [2,3,4]. 
                The values are _X[0,0,0]=0d0, _X[1,0,0]=1d0, ... 
                _X[1,2,3]=23d0. 
 
      See also. ARRAY, RANDOM, and ZERO."""
    min_args=0
    max_args=2
    name='RAMP'
    opcode=289

class RANDOM(_toBeCompleted):
    """      F90 Modified Transformation. 
      
      Generate an array of pseudorandom 
                numbers. 
 
      Arguments Optional: SHAPE, MOLD. 
        SHAPE   integer vector. 
        MOLD    numeric. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Type of MOLD and shape (dimensions) is SHAPE. If SHAPE 
                is absent, the result is a scalar. If MOLD is absent, 
                the result will be floats. 
 
      Result..  The result will be different with each call unless 
                RANDOMSEED is used. Integers are on the full range, 
                floating numbers are from 0 to 1. 
 
      Example.  _X = RANDOM(2,1d0) makes a vector of double precision 
                numbers with value 
                [.7043401852374758D0,.6857676661043094D0]. 
 
      See also. ARRAY, RAMP, and ZERO."""
    min_args=0
    max_args=2
    name='RANDOM'
    opcode=290

class RANGE(_toBeCompleted):
    """      F90 Inquiry. 
      
      The decimal exponent range in the model representing the 
                type of the argument. 
 
      Argument. X must be real or complex, scalar or array. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
      Result..  INT(MIN(LOG10(HUGE(X)),-LOG10(TINY(X)))). 
 
      Example.  RANGE(1.0) is 38 on VAX."""
    min_args=1
    max_args=1
    name='RANGE'
    opcode=141

class RANK(_toBeCompleted):
    """      Inquiry.  
      
      Number of dimensions, zero for scalar. 
 
      Argument. X is any VMS data type. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
 
      Result..  The number of dimensions of an array, zero fo a scalar. 
 
      Examples. RANK(3) is 0. RANK(RAMP([3,4])) is 2."""
    min_args=1
    max_args=1
    name='RANK'
    opcode=293

class RAW_OF(_toBeCompleted):
    """      MDS Operation. 
      
      Get the raw field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_SIGNAL, the raw field. 
                All others DATA(A). 
 
      Example.  RAW_OF(BUILD_SIGNAL(6*$VALUE,42)) is 42. 
 
      See also. $VALUE and $THIS for use of this within a signal."""
    min_args=1
    max_args=1
    name='RAW_OF'
    opcode=294

class REAL(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to real. 
 
      Arguments Optional: KIND. 
        A       numeric. 
        KIND    scalar integer type number, for example, KIND(1d0). 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  If KIND present, the type KIND; otherwise, the real 
                type with the same length. To get F, D, G, or H floating 
                result use F_FLOAT, etc. 
 
      Result..  Immediate at compilation. 
        (i)     A is integer or real, the result is the truncated 
                approximation. 
        (ii)    A is complex, the result is the approximation to the 
                real part. 
 
      Examples. REAL(-3) is -3.0. REAL(Z,Z) is real part of the complex. 
                This is done in TDISHR as REAL(Z). In F90, REAL(Z) sets 
                the default floating point size."""
    min_args=1
    max_args=2
    name='REAL'
    opcode=296

class REF(_toBeCompleted):
    """       CALL mode. Pass the data of the argument by reference.
       Argument. X is any type, scalar or array that DATA can evaluate.
       Use..... Starting address of VMS data, like Fortran %REF('123').
       The address of the DATA of the argument. For X alone, non-data
       forms may be passed. May programs cannot handle these forms.
       The REF form is expected by most Fortran routines but the DESCR
       form is used for characters."""
    min_args=1
    max_args=1
    name='REF'
    opcode=298

class REM(_toBeCompleted):
    """      Store a comment in an expression. No action is taken on the arguments. 
                REM(" ...") is a null operation that can retain a 
                comment; it must be where a null expression is valid. 
 
      Arguments Optional: COMMENT. 
        COMMENT,... any type. 
 
      Result..  None. 
 
      Example.  REM("addition example"),2+3 is 5."""
    min_args=1
    max_args=254
    name='REM'
    opcode=441

class REPEAT(_toBeCompleted):
    """      F90 Character Elemental. 
      
      Concatenate several copies of a string. 
 
      Arguments 
        STRING  character. 
        NCOPIES integer scalar, not negative. 
 
      Signals.  Same as STRING. 
      Units...  Same as STRING. 
      Form....  Character of length NCOPIES times that of STRING. 
 
      Result..  The concatenation of NCOPIES copies of STRING. 
      Examples. REPEAT('H',2) is "HH". 
                REPEAT('XYZ',0) is ""."""
    min_args=2
    max_args=2
    name='REPEAT'
    opcode=299

class REPLICATE(_toBeCompleted):
    """      Transformation. 
      
      Replicates an array by increasing a 
                dimension. 
 
      Arguments 
        ARRAY   any type. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
        NCOPIES integer scalar. 
      Signals.  Same as ARRAY except DIM-th dimension is removed. 
      Units...  Same as ARRAY. 
      Form....  Same type and rank as array with shape [E[0:DIM-1], 
                MIN(NCOPIES,0)*E[DIM],E[DIM+1:n]] where E is the shape 
                of ARRAY. 
 
      Result..  NCOPIES replications of the values of ARRAY. 
 
      Example.  REPLICATE([2 4],1,3) is [2 4 2 4 2 4]. 
                          [3 5]         [3 5 3 5 3 5] 
                Written as an expression the array is 
                Set_Range(2,2,[2,3,3,4]) and gives 
                Set_Range(2,6,[2,3,4,5, 2,3,4,5, 2,3,4,5]). 
                For DIM=0 it gives 
                Set_Range(6,2,[2,3, 2,3, 2,3, 4,5, 4,5, 4,5]). 
 
      See Also. REPEAT to concatenate copies of a string. 
                SPREAD to increase the number of dimensions."""
    min_args=3
    max_args=3
    name='REPLICATE'
    opcode=300

class RESET_PRIVATE(_toBeCompleted):
    """      Variables. 
      
      Frees all private variables of all levels and their memory. 
 
      Arguments None. 
 
      Result..  None. 
 
      Side Effect. All private variables are freed and forgotton. 
 
      Example.  RESET_PRIVATE()."""
    min_args=0
    max_args=0
    name='RESET_PRIVATE'
    opcode=376

class RESET_PUBLIC(_toBeCompleted):
    """      Variables.
      
      Frees all public variables and their memory. 
 
      Arguments None. 
 
      Result..  None. 
 
      Side Effect. All public variables are freed and forgotton. 
 
      Example.  RESET_PUBLIC()."""
    min_args=0
    max_args=0
    name='RESET_PUBLIC'
    opcode=377

class RETURN(_toBeCompleted):
    """      CC Modified Statement. 
      
      Return from a FUN with value. 
      
      Required Usual Form. RETURN (X);. 
      Function Form     RETURN(X). May be syntatically invalid. 
 
      Argument. Optional: X. 
        X       any. Unlike CC, the parentheses are required. 
      >>>>>>Note that a null is RETURN(*) or RETURN(). 
 
      Result..  X. 
 
      Example.  FUN(_A,_B) {RETURN(A*B);}"""
    min_args=0
    max_args=1
    name='RETURN'
    opcode=302

class ROUTINE_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the routine field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_CALL, the routine field. 
                DSC$K_DTYPE_ROUTINE, the routine field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='ROUTINE_OF'
    opcode=305

class RRSPACING(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      The reciprocal of the relative spacing of model          
                numbers near the argument value. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Same as X. 
 
      Result..  Value ABS(X*b^-e)*b^p, where b is the real base, e is 
                exponent part of X, and p is the number of digits in X. 
 
      Example.  RRSPACING(-3.0) is 0.75*2^24 on the VAX."""
    min_args=1
    max_args=1
    name='RRSPACING'
    CCodeName='RrSpacing'
    opcode=306

class SCALE(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      Changes X exponent by I, multiplying X by b^I. 
 
      Arguments 
        X       real or complex. 
        I       integer. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Same as X. 
 
      Result..  X*b^I, where b is the base of real model numbers, 
                provided the result is within range. 
 
      Example.  SCALE(3.0,2) is 12.0 on the VAX."""
    min_args=2
    max_args=2
    name='SCALE'
    opcode=307

class SCAN(_toBeCompleted):
    """      F90 Character Elemental. 
      
      Scan a string for a character in a set. 
 
      Arguments Optional: BACK. 
        STRING  character. 
        SET     character. 
        BACK    logical. 
 
      Signals.  Single signal or smallest data. 
      Units...  Same as STRING. 
      Form....  Integer type, compatible shape of all. 
 
      Result..  The result is -1 if STRING does not contain any of the 
                characters that are in SET of if the length of STRING or 
                SET is zero. 
        (i)     BACK is absent or false. The offset of the leftmost 
                character of STRING that is in SET. 
        (ii)    BACK present and true. The offset of the rightmost 
                character of STRING that is in SET. 
 
      Examples. SCAN('FORTRAN','TR') is 2. 
                SCAN('FORTRAN','TR',$TRUE) is 4. 
                SCAN('FORTRAN','BCD') is -1. 
 
      See also. VERIFY to check that all character are in a set."""
    min_args=2
    max_args=3
    name='SCAN'
    opcode=308

class SELECTED_INT_KIND(_toBeCompleted):
    """      F90 Inquiry. 
      
      The kind value of an integer that will 
                represent the number of decimal digits. 
 
      Argument. R must be a scalar integer. 
 
      Signality.        None. 
      Units...  None. 
      Form....  Scalar integer. 
 
      Result..  A value equal to the kind type parameter of an integer 
                data type that represents all values with between -10^R 
                and 10^R, or if no such kind is available, the result 
                is -1. If more than one kind meets the criteria, the 
                result is the one with the smallest range. 
 
      Example.  SELECTED_INT_KIND(6) is 8 (DSC$K_DTYPE_L) on the VAX."""
    min_args=1
    max_args=1
    name='SELECTED_INT_KIND'
    opcode=413

class SELECTED_REAL_KIND(_toBeCompleted):
    """      F90 Inquiry. 
      
      The kind value of an real that will 
                represent the number of decimal digits and the 
                decimal exponent range. 
 
      Argument. Optional: P and R must be a scalar integers. 
 
      Signality.        None. 
      Units...  None. 
      Form....  Scalar integer. 
 
      Result..  A value equal to the kind type parameter of a real 
                data type with decimal precision, as returned by 
                PRECISION, of at least P digits and exponent range, 
                as returned by RANGE of at least R. If no such kind 
                is available the result is -1 if the precision is not 
                available, -2 if the exponent is not available, or -3 if 
                neither. If more than one kind meets the criteria, the 
                result is the one with the smallest decimal precision. 
 
      Example.  SELECTED_REAL_KIND(6,30) is 10 (DSC$K_DTYPE_F) on the VAX."""
    min_args=1
    max_args=2
    name='SELECTED_REAL_KIND'
    opcode=414

class SET_EXPONENT(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      Model number whose fractional part is the 
                fractional part is that of X and 
                whose exponent part is I. 
 
      Arguments 
        X       real or complex. 
        I       integer. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Same as X. 
 
      Result..  X*b^(I-e), where b is the real number base and e is 
                exponent offset. 
 
      Example.  SET_EXPONENT(3.0,1) is 1.5 on the VAX."""
    min_args=2
    max_args=2
    name='SET_EXPONENT'
    opcode=310

class SET_RANGE(_toBeCompleted):
    """      Transformation. 
      
      Set array bounds and multipliers from a list. 
 
      Arguments Optional: BOUND,.... 
        BOUND,... integer scalar or range, they are taken from ARRAY 
                where omitted. 
        ARRAY   any type scalar, vector, or array. 
 
      Signals.  Same as ARRAY. 
      Units...  Same as ARRAY. 
      Form....  Same type as ARRAY with shape from the bounds list. Any 
                omitted bounds are picked from the corresponding bounds 
                of ARRAY. 
 
      Result..  Elements in array order from ARRAY. 
                Immediate at compilation even if all but last argument 
                are ranges and provided last argument is an array. 
 
      Examples.
 _A=SET_RANGE(2:3,5,1:10) is [1, 3, 5, 7, 9].
                             [2, 4, 6, 8, 10]
 SET_RANGE(-2:,:3,_A) has LBOUND(_A,0) of [-2,-1] and
                          UBOUND(_A,1) of [-1,3]."""
    min_args=2
    max_args=9
    name='SET_RANGE'
    opcode=311

class SHAPE(_toBeCompleted):
    """      F90 Inquiry. 
      
      The shape of an array or a scalar. 
 
      Arguments OPTIONAL: DIM (To follow F90 use SIZE with a DIM). 
        SOURCE  any type scalar, array, or signal. 
        DIM     integer scalar from 0 to n-1, where n is rank of SOURCE. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer vector of size equal to rank of SOURCE. 
 
      Result..  The declared shape of SOURCE 
                for subscript DIM of SOURCE. If no bounds were declared 
                it is one less than the multiplier for subscript DIM of 
                SOURCE. SHAPE(ARRAY) has value whose j-th component is 
                equal to SHAPE(ARRAY,j) for each j, 0 to n-1. 
 
      Examples. SHAPE(_A[2:5,-1:1]) is [4,3]. SHAPE(3) is [], a 
                zero-length vector. 
 
      See also  LBOUND for lower bound, UBOUND for upper bound, 
                SIZE for total elements, and E... for signals."""
    min_args=1
    max_args=2
    name='SHAPE'
    opcode=135

class SHIFT_LEFT(_toBeCompleted):
    """      Numeric Elemental. 
      
      Logical or arithmetic left shift of an element. 
      
      Usual Form        I << SHIFT. 
      Function Form     SHIFT_LEFT(I,SHIFT). 
 
      Arguments 
        I       must be integer. Octaword is not supported. 
        SHIFT   must be integer, must be positive. The low byte is used. 
 
      Signals.  Single signal or smaller data. 
      Units...  Same as I. 
      Form....  Type of I, compatible shape of all. 
 
      Result..  The bits of I shifted SHIFT positions left. 
        (i)     For unsigned numbers, the vacated bits are cleared. 
        (ii)    For signed numbers, an arithmetic shift if SHIFT is 
                from 0 to the size in bits; otherwise, undefined. 
 
      Examples. 
        (i)     0X12UB << 4 is 0X20UB. 
        (ii)    0X12SB << 4 is 0X20UB on the VAX."""
    min_args=2
    max_args=2
    name='SHIFT_LEFT'
    opcode=314

class SHIFT_RIGHT(_toBeCompleted):
    """      Numeric Elemental. 
      
      Logical or arithmetic right shift of an element. 
      
      Usual Form        I >> SHIFT. 
      Function Form     SHIFT_RIGHT(I,SHIFT). 
 
      Arguments 
        I       must be integer. Octaword is not supported. 
        SHIFT   must be integer. The low byte is used. 
 
      Signals.  Single signal or smaller data. 
      Units...  Same as I. 
      Form....  Type of I, compatible shape of all. 
 
      Result..  The bits of I shifted SHIFT positions right. 
        (i)     For unsigned numbers, the vacated bits are cleared. 
        (ii)    For signed numbers, the vacated bits are filled from the 
                sign bit (two's complement arithmetic shift). 
 
      Examples. 
        (i)     0X12UB >> 4 is 0X20UB. 
        (ii)    0X89SB >> 4 is 0XF8SB."""
    min_args=2
    max_args=2
    name='SHIFT_RIGHT'
    opcode=315

class SHOW_PRIVATE(_toBeCompleted):
    """      Variable IO. 
      
      Display on normal output the contents of a wildcard list 
                of variable names or all the variables. 
 
      Arguments Optional: STRING. 
        STRING,... character scalar with wildcards % and *. If omitted 
                all private variables are displayed. 
 
      Result..  None. 
 
      Side Effect. Writes to stdout, SYS$OUTPUT on the VAX. 
 
      Example.  _A = 42, SHOW_PRIVATE("_A") produces 
                Private _A      = 42"""
    min_args=0
    max_args=254
    name='SHOW_PRIVATE'
    opcode=378

class SHOW_PUBLIC(_toBeCompleted):
    """      Variable IO. 
      
      Display on normal output the contents of a wildcard list 
                of variable names or all the variables. 
 
      Arguments Optional: STRING. 
        STRING,... character scalar with wildcards % and *. If omitted 
                all public variables are written. 
 
      Result..  None. 
 
      Side Effect. Writes to stdout, SYS$OUTPUT on the VAX. 
 
      Example.  _A = 42, SHOW_PUBLIC("_A") produces 
                Public _A       = 42"""
    min_args=0
    max_args=254
    name='SHOW_PUBLIC'
    opcode=379

class SHOW_VM(_toBeCompleted):
    """       Show virtual memory consumption of this process"""
    min_args=0
    max_args=2
    name='SHOW_VM'
    opcode=380

class SIGNED(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to signed integer. 
      
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Signed integer of same length as real part of A. 
 
      Result..  The truncated integer. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  SIGNED(3LU) is 3."""
    min_args=1
    max_args=1
    name='SIGNED'
    opcode=317

class SIN(_completed):
    """      F90 Mathematical Elemental. 
      
      Sine of angle in radians. 
 
      Argument. X must be real or complex. HC is converted to GC. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to sin(X). Real X and 
                real part of complex X is in radians. 
 
      Example.  SIN(1.0) is 0.84147098, approximately."""
    min_args=1
    max_args=1
    name='SIN'
    opcode=318
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.sin(args[0].value))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],SIN(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for SIN function: %s" % (str(type(args[0])),))
        return ans

class SIND(_completed):
    """      Mathematical Elemental. 
      
      Sine of angle in radians. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to sin(X) with X in 
                degrees. 
 
      Example.  SIN(30.0) is 0.5, approximately."""
    min_args=1
    max_args=1
    name='SIND'
    opcode=319
    def _evaluate(self):
        args=self.evaluateArgs()
        if isinstance(args[0],_data.Scalar):
            ans = type(args[0])(_NP.sin(args[0].value/360.*2*_NP.pi))
        elif isinstance(args[0],_data.Signal):
            ans = _updateSignal(args[0],SIND(args[0].value).evaluate())
        else:
            raise _data.TdiException("Invalid argument type for SIN function: %s" % (str(type(args[0])),))
        return ans

class SINH(_toBeCompleted):
    """      F90 Mathematical Elemental. 
      
      Hyperbolic sine. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to sinh(X). 
 
      Example.  SINH(1.0) is 1.1752012, approximately."""
    min_args=1
    max_args=1
    name='SINH'
    opcode=320

class SIZE(_toBeCompleted):
    """      F90 Inquiry. 
      
      The extent an array or the total 
      declared number of elements in the array. 
 
      Arguments Optional: DIM. 
        ARRAY   any type array. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
 
      Result..  Equal to the declared extent of dimension DIM of ARRAY 
                or, if DIM is absent, the total declared number of 
                elements of ARRAY. 
 
      Examples. SIZE(_A[2:5,-1:1]),1) is 3. SIZE(_A[2:5,-1:1]) is 12. 
 
      See also  LBOUND for lower bound, SHAPE for number of elements, 
                UBOUND for upper bound, and E... for signals."""
    min_args=1
    max_args=2
    name='SIZE'
    opcode=136

class SIZEOF(_toBeCompleted):
    """      Inquiry. 
      
      Size of whole excluding descriptor. 
 
      Argument. Any VMS type. 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar. 
 
      Result..  The number of bytes in the evaluated expression. 
 
      Example.  SIZEOF(123) is 4."""
    min_args=1
    max_args=1
    name='SIZEOF'
    CCodeName='SizeOf'
    opcode=321

class SLOPE_OF(_toBeCompleted):
    """      MDS Operation. 
      
      Get the slope/delta field. 
 
      Arguments Optional: N. 
        A       descriptor as below. 
        N       integer scalar, from 0 to number of slope segments less 
                one. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_RANGE, the delta field or 1. 
                DSC$K_DTYPE_SLOPE, the N-th slope field. 
                Otherwise, an error. 
 
      Examples. SLOPE_OF(2..5) is 1. SLOPE_OF(1..10..0.5) is 0.5."""
    min_args=1
    max_args=2
    name='SLOPE_OF'
    opcode=322

class SORT(_toBeCompleted):
    """      Miscellaneous. 
      
      Make index list of ascending array. 
 
      Argument. 
        ARRAY   integer, real, or character. 
 
      Signals.  Same as ARRAY. 
      Units...  None. 
      Form....  Array of offsets. 
 
      Result..  The ascending order list of offsets, such that 
                MAP(A,SORT(A))[j] <= MAP(A,SORT(A))[j+1]. 
      >>>>>>>>>WARNING, equal values may not be in their original 
                order. This is may be true for all n*log2(n) sorts. 
 
      Examples. SORT([3,5,4,6]) is [0,2,1,3]. 
                SORT(['abc','ab','b']) is [1,0,2]. 
                _a=[3,5,4,6],MAP(_a,SORT(_a)) is [3,4,5,6]. 
 
      See also. SORTVAL to get sorted array without the index."""
    min_args=1
    max_args=2
    name='SORT'
    opcode=402

class SORTVAL(_toBeCompleted):
    """      Miscellaneous. 
      
      Rearrange element to make an ascending array. 
 
      Argument. 
        ARRAY   integer, real, or character. 
 
      Signals.  Same as ARRAY. 
      Units...  Same as ARRAY. 
      Form....  Same as ARRAY. 
 
      Result..  The ascending ordered list of values, such that 
                SORTVAL(ARRAY)[j] <= SORTVAL(ARRAY)[j+1] for all j. 
                This is the same as MAP(ARRAY,SORT(ARRAY)). 
 
      Examples. SORTVAL([3,5,4,6]) is [3,4,5,6]. 
                SORTVAL(['abc','ab','b']) is ['ab ','abc','b  ']. 
 
      See also. SORT to sort index. That index may be use for 
                several arrays. BSEARCH for a binary search."""
    min_args=1
    max_args=2
    name='SORTVAL'
    CCodeName='SortVal'
    opcode=325

class SPACING(_toBeCompleted):
    """      F90 Numeric Elemental. 
      
      Absolute spacing of model numbers near argument. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Same as X. 
 
      Result..  b^(e-p), where b is the base, e is the exponent part of 
                X and p is the digits of precision. 
 
      Example.  SPACING(3.0) is 2^-22 on the VAX."""
    min_args=1
    max_args=1
    name='SPACING'
    opcode=326

class SPAWN(_toBeCompleted):
    """      VMS IO. 
      
      Do commands or command file. 
 
      Arguments.        Optional: COMMAND, INPUT, OUTPUT 
        COMMAND character scalar of command to execute. 
        INPUT   character scalar name of file for SYS$INPUT. 
        OUTPUT  character scalar name of file as SYS$OUTPUT. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Status returned. 
 
      Result..  None. 
 
      >>>>>>>>>WARNING, side effects."""
    min_args=0
    max_args=3
    name='SPAWN'
    opcode=327

class SPREAD(_toBeCompleted):
    """      F90 Transformation. 
      
      Replicates an array by adding a dimension. 
      Broadcasts several copies of source along a specified dimension. 
 
      Arguments 
        SOURCE  any type, rank (n) must be less than 254. 
        DIM     integer scalar from 0 to n. 
        NCOPIES integer scalar. 
 
      Signals.  Same as ARRAY except that dimensions DIM and above are 
                moved up one and dimension DIM is empty. 
      Units...  Same as ARRAY. 
      Form....  Same type as SOURCE with shape [E[0:DIM-1], 
                MIN(NCOPIES,0),E[DIM:n]] where E is the shape of SOURCE. 
 
      Result..  The value of an element with subscripts [r0,r1,...rn] is 
                the value of the element of source with subscripts 
                [s0,...sn-1], where [s0,...sn-1] is [r0,...rn] with 
                subscript DIM omitted. 
 
      Example.  SPREAD([2,3,4],0,3) is the array [2 3 4]. 
                                                 [2 3 4] 
                                                 [2 3 4]"""
    min_args=3
    max_args=3
    name='SPREAD'
    opcode=328

class SQRT(_toBeCompleted):
    """     F90 Mathematical Elemental. 
      
      Square root. 
 
      Argument. X must be real or complex. HC is convert to GC. 
 
      Signals.  Same as X. 
      Units...  Half the count of each unit.(Today, bad if X has units.) 
      Form....  Same as X. 
 
      Result. The processor approximation to the square root of X. 
                A complex result is the principal value with the real 
                part greater that or equal to zero. When the real part 
                is 0, the imaginary part is >= 0. 
 
      Example.  SQRT(4.0) is 2.0, approximately."""
    min_args=1
    max_args=1
    name='SQRT'
    opcode=329

class SQUARE(_toBeCompleted):
    """      Numeric Elemental. Product of number with itself. 
 
      Argument. X must be numeric. 
 
      Signals.  Same as X. 
      Units...  Same as X * X. 
      Form....  Same as X. 
 
      Result..  X * X. 
 
      Example.  SQUARE(3) is 9."""
    min_args=1
    max_args=1
    name='SQUARE'
    opcode=330

class STATEMENT(_toBeCompleted):
    """      CC Statement. 
      
      Hold multiple statements as if one. 
      
      Required Usual Form. {STMT ...}. 
      Function Form     STATEMENT(STMT,...) May be syntatically invalid. 
 
      Arguments STMT,... must be statements. Simple statements end with 
                a semicolon (;), compound statements are in braces ({}). 
 
      Result..  None. 
 
      Example.  IF (_X[2]) { 
                        _B = 2; 
                        _C = 3; 
                }."""
    min_args=0
    max_args=254
    name='STATEMENT'
    opcode=331

class STRING_OPCODE(_toBeCompleted):
    """      MDS Character Elemental. 
      
      Convert string to an opcode value. 
 
      Argument. STRING must be character. 
 
      Signals.  Same as STRING. 
      Units...  None, bad if STRING has units. 
      Form....  Unsigned word. 
 
      Result..  The number associated with the opcode name. 
                Opcode names are like "OPC$STRING_OPCODE". 
 
      Example.  STRING_OPCODE('$') is 0."""
    min_args=1
    max_args=1
    name='STRING_OPCODE'
    opcode=334

class SUBSCRIPT(_toBeCompleted):
    """      CC-F90 Modified Operation. 
      
      Pick certain element of an expression. 
      
      Usual Form        X[ SUB,... ]. (The Brackets are required.) 
      Function Form     SUBSCRIPT(X,[SUB],...). 
 
      Arguments Optional: SUB,.... 
        X       array or signal. 
        SUB,... ranges, vector lists, scalars. 
      >>>>>>>>>WARNING, the number of subscripts must not exceed 
                the rank of X. 
      >>>>>>>>>WARNING, if X is a signal and the subscripted dimension 
                exists and SUB is a explicit 
                range without a delta, then all valid subscripts 
                between the begin and end values of the range 
                are used. This behavior may be forced for more 
                complex expressions of SUB by using $VALUE as 
                the delta of a range. 
 
      Signals.  Same as X. The trailing scalar axes are removed. 
                For non-trailing-scalar axes the axis is valid values 
                selected to match the SUB values. 
      Units...  Same as X. 
      Form....  Type of X and shape dependent on number of valid 
                elements in each subscript. 
 
      Result..  The selected values from X. For signals, the SUB values 
                are truncated by CULL and converted by X_TO_I to 
                indices. The nearest integral value is used. For 
                non-signals, the values are culled and used to select 
                values from X. 
 
      Examples. [1,2,3][2] is 3. [1,2,3][3] is [] a null vector. 
                Build_signal(1:100,*,build_dim(*,.01:1:.01))[.2:.25] 
                is build_signal([20,21,22,23,24,25],*, 
                [.2,.21,.22,.23,.24,.25]). 
 
      See also. EXTEND to continue endpoint values to prevent culling. 
                MAP to use offsets into the array X. 
                NINT to round indices to the nearest integers."""
    min_args=1
    max_args=9
    name='SUBSCRIPT'
    opcode=335

class SUBTRACT(_toBeCompleted):
    """      Numeric Elemental. 
      
      Subtract numbers. 
      
      Usual Form        A - B. 
      Function Form     SUBTRACT(A,B). 
 
      Arguments A and B must be numeric. 
 
      Signals.  Single signal or smaller data. 
      Units...  Single or common units, else bad. 
      Form....  Compatible form of A and B. 
 
      Result..  The element-by-element difference of objects A and B. 
      >>>>>>>>>WARNING, integer overflow is ignored. 
 
      Example.  [2,3,4] - 5.0 is [-3.0,-2.0,-1.0]."""
    min_args=2
    max_args=2
    name='SUBTRACT'
    opcode=336

class SUM(_toBeCompleted):
    """      F90 Transformation. 
      
      Sum of all the elements of ARRAY along dimension 
                DIM corresponding to the true elements of MASK. 
 
      Arguments Optional: DIM, MASK. 
        ARRAY   numeric array. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
        MASK    logical and conformable to ARRAY. 
 
      Signals.  Same as ARRAY if DIM-th or all dimensions omitted. 
      Units...  Same as ARRAY. 
      Form....  Same type as ARRAY. It is a scalar if DIM is absent or 
                ARRAY is scalar or vector. Otherwise, the result is an 
                array of rank n-1 and shaped like ARRAY with DIM 
                subscript omitted. 
 
      Result..  The result without DIM is the sum of the elements of 
                ARRAY, using only those with true MASK values and value 
                not equal to the reserved operand ($ROPRAND). With DIM, 
                the value of an element of the result is the sum of the 
                ARRAY elements with dimension DIM fixed as the element 
                number of the result. If no value is found, 1 is given. 
 
      Examples. SUM([1,2,3]) is 6. SUM(_C,,_C GT 0) finds the sum of all 
                positive element of C. 
		  If 
		_B=[[1, 3, 5],[2, 4, 6]]
                SUM(_B,0) is [9,12] and SUM(_B,1) is [3,7,11]."""
    min_args=1
    max_args=3
    name='SUM'
    opcode=337

class SWITCH(_toBeCompleted):
    """      CC Statement. 
      
      Select from cases presented in the statement. 
      
      Required Usual Form. SWITCH (X) STMT. 
      Function Form     SWITCH(X,STMT,...). May be syntatically invalid. 
 
      Arguments 
        X       any scalar that can be compared. 
        STMT    statement, simple or {compound}. 
      >>>>>>WARNING, multiple statements in call form are considered 
                to be in braces. 
 
      Result..  None. 
 
      Example.  SWITCH (_k) { 
                CASE (1) _j=_THING1; BREAK; 
                CASE (4.5:5.5) _j=_OTHER_THING; BREAK; 
                CASE DEFAULT ABORT(); 
                }. """
    min_args=2
    max_args=254
    name='SWITCH'
    opcode=338

class TAN(_toBeCompleted):
    """      F90 Mathematical Elemental.
      
      Tangent. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to tan(X), with X in radians. 
 
      Example.  TAN(1.0) is 1.5574077, approximately."""
    min_args=1
    max_args=1
    name='TAN'
    opcode=340

class TAND(_toBeCompleted):
    """      F90 Mathematical Elemental. 
      
      Tangent in degrees. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to tan(X), with X in degrees. 
      Example.  TAN(45.0) is 1.0, approximately."""
    min_args=1
    max_args=1
    name='TAND'
    opcode=341

class TANH(_toBeCompleted):
    """      F90 Mathematical Elemental. 
      
      Hyperbolic tangent. 
 
      Argument. X must be real. Complex numbers are an error. 
 
      Signals.  Same as X. 
      Units...  None, bad if X has units. 
      Form....  Same as X. 
 
      Result..  Processor approximation to tanh(X). 
      Example.  TANH(1.0) is 0.76159416, approximately. """
    min_args=1
    max_args=1
    name='TANH'
    opcode=342

class TASK_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the task field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_ACTION, the task field. 
                DSC$K_DTYPE_PROCEDURE, unchanged.. 
                DSC$K_DTYPE_PROGRAM, unchanged.. 
                DSC$K_DTYPE_ROUTINE, unchanged.. 
                DSC$K_DTYPE_METHOD, unchanged.. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='TASK_OF'
    opcode=343

class TEXT(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to text of given length. 
 
      Arguments Optional: LENGTH. 
        X       numeric or character. 
        LENGTH  integer scalar. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Character of given length or length associated with the 
                type of X. These are used B/BU 4, W/WU 8, L/LU 12, 
                Q/QU 20, O/OU 36, F 16, D/G 24, H 40, FC 32, DC/GC 48, 
                and HC 80. 
 
      Result..  A character string that represent the number. 
                (As of now, quadword and octaword are converted to hex.) 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  TEXT(1.2) is "   0.1200000E+02"."""
    min_args=1
    max_args=2
    name='TEXT'
    opcode=344

class TIME_OUT_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the time_out field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_METHOD, time_out field. 
                DSC$K_DTYPE_PROCEDURE, time_out field. 
                DSC$K_DTYPE_PROGRAM, time_out field. 
                DSC$K_DTYPE_ROUTINE, time_out field. 
                Otherwise, an error. """
    min_args=1
    max_args=1
    name='TIME_OUT_OF'
    CCodeName='TimeoutOf'
    opcode=345
    partnames=('timeout',)

class TINY(_toBeCompleted):
    """      F90 Inquiry. 
      
      The smallest positive number in the model representing 
                numbers of the type of the argument. 
 
      Argument. X must be real or complex. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Scalar of same type as real part of X. 
 
      Result..  The result is 1 if X is integer and b^(emin-1) if X is 
                real, where b is the real base and emin is the minimum 
                exponent in model numbers like X. 
 
      Example.  TINY(1.0) is 2^-128 on the VAX."""
    min_args=1
    max_args=1
    name='TINY'
    opcode=346

class TRANSLATE(_toBeCompleted):
    """      Character Elemental. 
      
      Replace matching characters with others. 
 
      Arguments 
        STRING  character. 
        TRANSLATION character. 
        MATCH   character. 
 
      Signals.  That of dominant shape. 
      Units...  Same as STRING. 
      Form....  Character of compatible shape. 
 
      Result..  For each character of STRING found in MATCH the 
                corresponding character in TRANSLATION replaces it. 
 
      Example.  TRANSLATE('ABCDEF','135','ACE') is "1B3D5F"."""
    min_args=3
    max_args=3
    name='TRANSLATE'
    opcode=381

class TRIM(_toBeCompleted):
    """      F90 Transformation. 
      
      The argument with trailing blank characters 
                removed, including tabs. 
 
      Argument. STRING is character scalar. 
 
      Signals.  Same as STRING. 
      Units...  Same as STRING. 
      Form....  Character with a length that is the length less the 
                number of trailing blanks (and tabs) in STRING. 
 
      Result..  Same as STRING except any trailing blanks are removed. 
                If STRING contains no nonblank characters, the result 
                has zero length. 
 
      Example.  TRIM(' A B  ') is " A B". 
 
      See also. ADJUSTL and ADJUSTR to justify strings."""
    min_args=1
    max_args=1
    name='TRIM'
    opcode=349

class UBOUND(_toBeCompleted):
    """      F90 Inquiry. 
      
      All the lower bounds of an array or a specified 
                lower bound. 
 
      Arguments Optional: DIM. 
        ARRAY   any type array. 
        DIM     integer scalar from 0 to n-1, where n is rank of ARRAY. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Integer scalar if DIM present, 
                otherwise, vector of size n. 
      Result..  UBOUND(ARRAY,DIM) is equal to the declared lower bound 
                for subscript DIM of ARRAY. If no bounds were declared 
                it is one less than the multiplier for subscript DIM of 
                ARRAY. UBOUND(ARRAY) has value whose j-th component is 
                equal to UBOUND(ARRAY,j) for each j, 0 to n-1. 
 
      Example.  UBOUND(_A=SET_RANGE(2:3,7:10,0)) is [3,10] and 
                UBOUND(_A,1) is 10. 
 
      See also  LBOUND for lower bound, SHAPE for number of elements, 
                SIZE for total elements, and E... for signals."""
    min_args=1
    max_args=2
    name='UBOUND'
    opcode=138

class UNARY_MINUS(_toBeCompleted):
    """      Numeric Elemental. 
      
      Negate a number. 
      
      Usual Form        - X. 
 
      Argument. X must be numeric. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Same as X except unsigned become signed. 
 
      Result..  Negate each element. 
                (Two's complement for integers on VAX.) 
                Immediate at compilation. 
 
      Example.  -2LU is -2."""
    min_args=1
    max_args=1
    name='UNARY_MINUS'
    opcode=350

class UNARY_PLUS(_toBeCompleted):
    """      Numeric Elemental. 
      
      Make a signed number. (Generally unneeded.) 
      
      Usual Form        + X. 
 
      Argument. X must be numeric. 
 
      Signals.  Same as X. 
      Units...  Same as X. 
      Form....  Same as X except unsigned become signed. 
 
      Result..  Make number of each element. 
                Immediate at compilation. 
 
      Example.  +2LU is 2."""
    min_args=1
    max_args=1
    name='UNARY_PLUS'
    opcode=351

class UNION(_toBeCompleted):
    """      Transformation. 
      
      The union of sets, keeping only unique values. 
 
      Arguments Any sortable data types--character, integer, or real. 
 
      Signals.  None. 
      Units...  The combined type of all arguments. 
      Form....  The compatible type of all arguments. 
 
      Result..  The A's are combined by VECTOR and sorted. Duplicates 
                are removed. 
 
      Example.  UNION([4,5],[2,3,5]) is [2,3,4,5]."""
    min_args=0
    max_args=254
    name='UNION'
    opcode=352

class UNITS(_toBeCompleted):
    """      MDS Operation. 
      
      Get the data of the units field or a blank. 
 
      Argument. Expression that is evaluated. 
 
      Result..  DSC$K_DTYPE_DIMENSION, UNITS(axis field). 
                DSC$K_DTYPE_RANGE, combined UNITS of the fields. 
                DSC$K_DTYPE_SLOPE, combined UNITS of the fields. 
                DSC$K_DTYPE_WINDOW, UNITS(value_at_idx0 field). 
                DSC$K_DTYPE_WITH_UNITS, DATA(units field). 
                else removing SIGNAL, PARAM, and such. 
                Otherwise, a single blank is returned, an empty string 
                cannot be used by IDL. 
                This recursive definition will find the first WITH_UNITS 
                field available. 
      >>>>>>>>>WARNING, types for which DATA is undefined give an error. 
 
      Example.  Let _A=BUILD_WITH_UNITS(42,'m'//'/s'), 
                then UNITS(_A) is "m/s"."""
    min_args=1
    max_args=1
    name='UNITS'
    opcode=353

class UNITS_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the units field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_WITH_UNITS, the units field. 
                Otherwise, a single blank is returned. 
 
      Examples. UNITS_OF(BUILD_WITH_UNITS(42.,"V")) is "V". 
                UNITS_OF(42) is " "."""
    min_args=1
    max_args=1
    name='UNITS_OF'
    opcode=354

class UNSIGNED(_toBeCompleted):
    """      Conversion Elemental. 
      
      Convert to unsigned integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Unsigned integer of same length as real part of A. 
      Result..  The truncated integer. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Example.  UNSIGNED(2.783) is 2LU."""
    min_args=1
    max_args=1
    name='UNSIGNED'
    opcode=356

class UPCASE(_toBeCompleted):
    """      Character Elemental. 
      
      Change all alphabetics to uppercase. 
      
      Argument. STRING must be character. 
 
      Signals.  Same as STRING. 
      Units...  Same as STRING. 
      Form....  Same as STRING. 
 
      Result..  The same as STRING with all lower case alphabetics 
                replaced by the corresponding uppercase character. 
 
      Example.  UPCASE('Name') is "NAME"."""
    min_args=1
    max_args=1
    name='UPCASE'
    opcode=383

class USING(_toBeCompleted):
    """      MDS Operation. 
      
      Evaluate expression from a different tree location. 
 
      Arguments Optional: DEFAULT, SHOTID, EXPT. 
        A       an expression. 
      >>>>>>>>>WARNING, pathnames in the expression A will be relative to the 
                temporary tree location and may not be related to the 
                old tree. 
        DEFAULT character, NID, long, or PATH scalar. The new tree path. 
      >>>>>>>>>WARNING, relative paths are like the full name in the old tree. 
        SHOTID  integer scalar. The shot number. 
        EXPT    character scalar. The experiment name. 
 
      Result..  Depends on the expression at the node in the new tree. 
                The old node, shot, and experiment are used to evaluate 
                the expressions for DEFAULT, SHOTID, and EXPT. If SHOTID 
                or EXPT present, a new tree is opened for reading. The 
                temporary path is set from DEFAULT. If omitted, the 
                values used are those of the current tree and path. 
                There will be an error if the old tree is not open or 
                the old path is bad. 
 
      Example.  Say shot 1234 is a "vacuum" subtraction shot for the 
                current shot and we are positioned at \TOP.XRAY:CHAN_01, 
                which has data, then the subtracted data might be 
                        :DATA - USING(:DATA,,1234)"""
    min_args=2
    max_args=4
    name='USING'
    opcode=384

class VAL(_toBeCompleted):
    """      CALL mode. 

      Pass the data of the argument by value.

      Argument.   X is any type, scalar or array that DATA can evaluate.

      Use.....    Integer scalar like a CC call or Fortran %VAL(123). The
                  value of the DATA of the argument used like an address."""
    min_args=1
    max_args=1
    name='VAL'
    opcode=357

class VALIDATION(_toBeCompleted):
    """      MDS Operation. 
      
      Evaluate the validation field of a parameter. 
 
      Argument. PARAM must be or make a param. 
 
      Result..  Sets $THIS to the parameter and sets $VALUE to the 
                value field of the param and 
                does DATA(validation field). 
 
      Example.  Let _A=BUILD_PARAM(42,"text of this param",$VALUE<6), 
                then VALIDATION(_A) is $FALSE."""
    min_args=1
    max_args=1
    name='VALIDATION'
    opcode=385

class VALIDATION_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the validation field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for this: 
                DSC$K_DTYPE_PARAM, the validation field. 
                Otherwise, an error. 
      >>>>>>>>>WARNING, because the validation field is likely to use 
                $VALUE or $THIS, DATA(VALIDATION_OF(parmeter)) will not 
                work. Use VALIDATION(parameter) for the correct result. 
 
      Example.  VALIDATION_OF(BUILD_PARAM(42,"the answer",$VALUE>6)) is 
                $VALUE>6, which cannot be evaluated."""
    min_args=1
    max_args=1
    name='VALIDATION_OF'
    opcode=358

class VALUE_OF(_toBeCompleted):
    """      MDS Operation. 
      
      Get the value field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_DIMENSION, VALUE_OF(window field). 
                DSC$K_DTYPE_PARAM, the value field. 
                DSC$K_DTYPE_SIGNAL, the data field. 
                DSC$K_DTYPE_WINDOW, the value_at_idx0 field. 
                DSC$K_DTYPE_WITH_UNITS, the data field. 
                Otherwise, DATA(A). 
      >>>>>>>>>WARNING, because the data field of a signal is likely to 
                use $VALUE, DATA(VALUE_OF(signal)) may not work. 
                Use DATA(signal) instead. 
 
      Example.  VALUE_OF(BUILD_PARAM(42,"the answer",$VALUE>6)) is 42."""
    min_args=1
    max_args=1
    name='VALUE_OF'
    opcode=359

class VAR(_toBeCompleted):
    """      Variables.
      
      Specifies a private or public variable by textual name. 
 
      Argument. Optional: REPLACE. 
        STRING  the character scalar name of a variable. 
      >>>>>>>>>WARNING, all names that do not begin with an underscore (_) or 
                dollar sign ($) cannot be accessed other than by VAR. 
                $-names are reserved for system names. 
        REPLACE the new value of STRING. 
 
      Result..  That of the old contents of the variable. 
 
      Example.  _A=42,VAR("_A") is 42."""
    min_args=1
    max_args=2
    name='VAR'
    opcode=360

class VECTOR(_toBeCompleted):
    """      F90 Modified Transformation. 
      
      Form a vector or array from scalar, 
                vector, array, range, and promote inputs. 
      
      Usual Form        [X,...]. 
                For F90 compatiblity, (/ is [ and /) is ]. 
 
      Arguments Must be compatible types. 
 
      Signals.  Single signal or smallest data. 
      Units...  Single or common units, else bad. 
      Form....  Type of highest data type found. The size is the sum of 
                the sizes of all the arguments. 
                If the shapes of all arguments are the same, the result 
                has one more dimension, the last, of size equal to the 
                number of arguments. F90 defines only a vector result. 
 
      Result..  A vector with all the values in the arguments. 
                Immediate at compilation. 
 
      Examples. [2,3:5,4@6] is [2,3,4,5,6,6,6,6]. 
                [[1,2],[3,4],5:6] is [1 3 5], long array shaped [2,3]. 
                                     [2 4 6] 
                1:3 is a vector, [1:3] is an array of shape [1,3], 
                so don't use extraneous brackets."""
    min_args=0
    max_args=254
    name='VECTOR'
    opcode=361

class VERIFY(_toBeCompleted):
    """      F90 Character Elemental. 
      
      Verify that a set of characters has all the 
                character in a string. 
 
      Arguments Optional: BACK. 
        STRING  character. 
        SET     character. 
        BACK    logical. 
      Signals.  Single signal or smaller data. 
      Units...  Same as STRING. 
      Form....  Integer type, compatible shape of all. 
 
      Result..  The result is -1 if STRING contains only the characters 
                that are in SET of if the length of STRING or SET is 0. 
        (i)     BACK is absent or false. The offset of the leftmost 
                character of STRING that is not in SET. 
        (ii)    BACK present and true. The offset of the rightmost 
                character of STRING that is not in SET. 
 
      Examples. VERIFY('ABBA','AB') is -1. 
        (i)     VERIFY('ABBA','A') is 1. 
        (ii)    VERIFY('ABBA','A',$TRUE) is 2. 
 
      See also. SCAN to find a character in a set."""
    min_args=2
    max_args=3
    name='VERIFY'
    opcode=362

class WAIT(_toBeCompleted):
    """      IO. 
      
      Suspend processing for at least the time given. 
 
      Argument. SECONDS must be real scalar. 
 
      Result..  None. 
 
      Example.  WAIT(3.5) delays 3 and 1/2 seconds. this might retain 
                a plot or comment for a short time."""
    min_args=1
    max_args=1
    name='WAIT'
    opcode=363

class WHEN_OF(_PART_OF):
    """      MDS Operation. 
      
      Get the when field. 
 
      Argument. Descriptor as below. 
 
      Result..  DISPATCH_OF(A) is searched for this: 
                DSC$K_DTYPE_DISPATCH, the when field. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='WHEN_OF'
    opcode=364

class WHILE(_toBeCompleted):
    """      CC Statement. 
      
      Repeat while expression is true. 
      
      Require Usual Form. WHILE (TEST) STMT. 
      Function Form     WHILE(TEST,STMT,...). May be syntatically invalid. 
 
      Arguments 
        TEST    logical scalar. 
        STMT    statement, simple or {compound}. 
      >>>>>>WARNING, multiple statements in call form are considered 
                to be in braces. 
      Result..  None. 
 
      Example.  WHILE (RANDOM()<0.99) ++_J;"""
    min_args=2
    max_args=254
    name='WHILE'
    opcode=366

class WINDOW_OF(_PART_OF):
    """      MDS Operation.
      
      Get the window field. 
 
      Argument. Descriptor as below. 
 
      Result..  A is searched for these: 
                DSC$K_DTYPE_DIMENSION, the window field. 
                DSC$K_DTYPE_WINDOW, unchanged. 
                Otherwise, an error."""
    min_args=1
    max_args=1
    name='WINDOW_OF'
    opcode=367

class WORD(_toBeCompleted):
    """      Conversion Elemental.
      
      Convert to word (two-byte) integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Word-length integer. 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. WORD(123) is 123W. WORD(65537) is 1W."""
    min_args=1
    max_args=1
    name='WORD'
    opcode=368

class WORD_UNSIGNED(_toBeCompleted):
    """      Conversion Elemental.
      
      Convert to word (two-byte) unsigned integer. 
 
      Argument. A must be numeric. 
 
      Signals.  Same as A. 
      Units...  Same as A. 
      Form....  Word-length unsigned integer. 
 
      Result..  The truncated whole part of A. 
                Immediate at compilation. 
      >>>>>>>>>WARNING, truncation does not cause an error. 
 
      Examples. WORD_UNSIGNED(123) is 123WU. 
                WORD_UNSIGNED(65537) is 1WU."""
    min_args=1
    max_args=1
    name='WORD_UNSIGNED'
    opcode=369

class WRITE(_toBeCompleted):
    """WRITE ([UNIT],[ARG]...)
      IO.       
      
      Writes text values to terminal or file. 
 
      Arguments Optional UNIT,ARG... 
        UNIT    Character scalar or * for stdout. 
        ARG...  Any type. 
 
      Result..  Numeric or text scalars and arrays are converted to 
                text and output to the selected UNIT. Arrays are 
                on separate lines; scalars are packed without space 
                up to the terminal line width. If the data type or 
                class if nonstandard, DECOMPILE is used to make a 
                text string that is output. 
      >>>>>>>>>WARNING, No explicit formatting is provided. You can use 
                CVT(-1.2,"12345678") to get a string "-1.2E+00" or 
                DECOMPILE(-1.2) to get "-1.2". 
 
      Example.. WRITE(*,'x=',1.2,3,[4,5],6) appears as 
                x= 1.20000E+00           3 
                           4           5 
                           6"""
    min_args=1
    max_args=254
    name='WRITE'
    opcode=370

class X_TO_I(_toBeCompleted):
    """      MDS Transform Elemental.
      
      Convert index into axis values. 
 
      Arguments Optional X. 
        DIMENSION a dimension with optional window and axis. 
                If DIMENSION is missing, the unchanged X is returned. 
                If the window of DIMENSION is missing, the first 
                axis point is assigned an index of 0. 
        X       scalar or array list of axis values. 
                (For TDI$X_TO_I, the fake address of -1 for X, 
                returns a 2-element vector with the index bounds.) 
 
      Signals.  Same as X. 
      Units...  Same as axis of DIMENSION. 
      Form....  Same type as DATA(axis). Same shape as X. 
 
      Result..  The window and axis are evaluated for each axis point X. 
                The result is the index value of that point. 
                Although the window start and end indices may be used 
                to determine the value of axis points, they do not 
                limit the range of results. 
 
      Examples. X_TO_I(BUILD_DIM(BUILD_WINDOW(2,5,1.1), 
                BUILD_RANGE(,,3))) is [2,3,4,5] corresponding to axis 
                [7.1,10.1,13.1,16.1]. 
                X_TO_I(BUILD_DIM(BUILD_WINDOW(2,7,1.1), 
                BUILD_RANGE(,,3)),[4.1,7.1,10.1,13.1]) is [1.,2.,3.,4.]. 
                The index 1 (axis point 4.1) is outside the valid 
                window of 2 to 7. 
 
      See also. CULL and EXTEND to discard or limit axis points. 
                I_TO_X for the inverse transform. 
                NINT to round indices to the nearest integers."""
    min_args=1
    max_args=2
    name='X_TO_I'
    opcode=393
    CCodeName='XtoI'

class XD(_toBeCompleted):
    """      CALL mode. 

      Pass the data of the argument by extended descriptor.
                  This is the only form that can pass signals and other
                  class-R described data.

      Argument.   X is any VMS or MDS type that can be EVALUATED.

      Use.....    Only routines written with MDS calls can use these
                  descriptors."""
    min_args=1
    max_args=1
    name='XD'
    opcode=400

class ZERO(_toBeCompleted):
    """      Transformation.
      
      Generate an array of zeroes. 
 
      Arguments Optional: SHAPE, MOLD. 
        SHAPE   integer vector. 
        MOLD    any numeric. 
 
      Signals.  None. 
      Units...  None. 
      Form....  Type of MOLD and shape (dimensions) is SHAPE. 
                If SHAPE is absent, the result is a scalar. 
                If MOLD is absent, the result will be longs. 
      Result..  The value of each element is 0. 
 
      Example.  _X = ZERO([2,3,4],1d0) makes an array of 
                double precision floating point numbers of shape 
                [2,3,4]. They are all 0d0. 
 
      See also. ARRAY, RAMP, and RANDOM. """
    min_args=0
    max_args=2
    name='ZERO'
    opcode=371
################## The following are defined in tdishr but not implemented in tdishr ###########
############################## included for compatibility with tdishr #########################
class BACKSPACE(NotSupported):
    """IO. Backspaces one record. ??"""
    min_args=1
    max_args=1
    name='BACKSPACE'
    opcode=62

class COMPILE_DEPENDENCY(NotSupported):
    min_args=1
    max_args=1
    name='COMPILE_DEPENDENCY'
    opcode=395

class CONVOLVE(NotSupported):
    """       Transformation. Convolve two vectors. 
    Arguments X and Y must be numeric vectors. 
    Signals. Single signal or smaller data. 
    Units... Same as X * Y.(??) 
    Form.... The compatible form. A vector of the ?? size. 
    
    Result.. ??"""
    min_args=2
    max_args=2
    name='CONVOLVE'
    opcode=105

class CSHIFT(NotSupported):
    """ F90 Transformation. Perform a circular shift on an array expression of 
rank one of perform circular shifts on all the complete 
rank one sections along a given dimension of an array 
expression of rank 2 or greater. Elements shifted out at 
one end of a section are shifted in at the other end. 
Different sections may be shifted by different amounts 
and in different directions. ?? 

Arguments Optional: DIM. 
ARRAY any type array. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 
SHIFT integer scalar for rank one; otherwise, it must be an 
array of rank n-1 and shape like ARRAY without dimension 
DIM. 

Signals. Same as ARRAY. 
Units... Same as ARRAY. 
Form.... Same as ARRAY. 

Result. 
(i) For a shift of k, element j of the result is ARRAY(j+k) 
with j+k reduced by adding or subtracting the dimension 
to give a number allowed for the subscript. 
(ii) For multiple dimensions, the result is the same as 
shifting each element of the n-1 dimensional section. 

Examples. 
(i) CSHIFT([1,2,3,4,5,6],2) is [3,4,5,6,1,2] and 
CSHIFT([1,2,3,4,5,6],-2) is [5,6,1,2,3,4]. 
(ii) CSHIFT(_M=[A B C],-1,1) is [C A B], 
[D E F] [F D E] 
[G H I] [I G H] 
CSHIFT(_M,2,[-1,1,0]) is [C A B]. 
[E F D] 
[G H I]     min_args=2"""
    max_args=3
    name='CSHIFT'
    opcode=110

class DATE_AND_TIME(NotSupported):
    """F90 Modified IO. Integer data from the date available to the processor 
and a real-time clock. 

Argument. STRING is character name of option. Options are 
DATE (9 characters) 
TIME (10 characters) 
ZONE (5 characters) or 
VALUES (8 integers) the default. 

Signals. Same as STRING. 
Units... None, bad if STRING has units. 
Form.... Character string or integer vector. 

Result.. If data is unavailable -HUGE(0), else: 
VALUES(0) Gregorian year, e.g., 1990 
VALUES(1) month 1 to 12 
VALUES(2) day of month 1 to 31 
VALUES(3) minutes local time is in advance of UTC 
VALUES(4) hour of day 0 to 23 
VALUES(5) minute of hour 0 to 59 
VALUES(6) second of minute 0 to 59 
VALUES(7) milliseconds 0 to 999 

Example. If called in Geneva, Switzerland on 1985 April 12 at 
15:27:35.5 would return 19850412 for 'DATE' 
152735.500 for 'TIME', +0100 for 'ZONE' and 
[1985,4,12,60,15,27,35,500] for the default."""
    min_args=0
    max_args=1
    name='DATE_AND_TIME'
    opcode=113

class DECODE(NotSupported):
    """Miscellaneous. ?? """
    min_args=1
    max_args=2
    name='DECODE'
    opcode=118

class DECOMPILE_DEPENDENCY(NotSupported):
    min_args=1
    max_args=1
    name='DECOMPILE_DEPENDENCY'
    opcode=396

class DERIVATIVE(NotSupported):
    """Transformation. The slope along a dimension with optional smoothing. ?? 

Arguments Optional: DIM, WIDTH. 
ARRAY numeric array. Signal uses dimension. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 
WIDTH real scalar. 

Signals. Same as ARRAY. 
Units... Same as for ARRAY/DIM_OF(ARRAY,DIM). (Today, ARRAY's.) 
Form.... Same as ARRAY. 

Result.. ??"""
    min_args=2
    max_args=3
    name='DERIVATIVE'
    opcode=122

class ENCODE(NotSupported):
    """Miscellaneous. Format values to text.??"""
    min_args=1
    max_args=254
    name='ENCODE'
    opcode=146

class ELSEWHERE(NotSupported):
    min_args=0
    max_args=0
    name='ELSEWHERE'
    opcode=145

class ENDFILE(NotSupported):
    """F90 IO. Mark end of file.?? """
    min_args=1
    max_args=1
    name='ENDFILE'
    opcode=147

class EOSHIFT(NotSupported):
    """F90 Transformation. Perform an end-off shift on an array expression of 
rank one or perform end-off shifts on all the complete rank-one 
sections along a given dimension of an expression of rank two or 
greater. 

Arguments Optional: BOUNDARY, DIM. 
ARRAY numeric or character array. 
SHIFT integer scalar if ARRAY is rank 1; otherwise, an integer 
array of rank n-1 array of shape like ARRAY with DIM 
dimension omitted. 
BOUNDARY same type as ARRAY and must be scalar if ARRAY is rank 
one; otherwise, a scalar or rank n-1 array shaped like 
ARRAY without dimension DIM. Default value is 0 for 
numerics and blanks for text. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 

Signals. Same as ARRAY. 
Units... Same as ARRAY. 
Form.... Same as ARRAY. 

Result.. Element [s0,s1,...sn-1] of the result is 
ARRAY[s0,s1,...sDIM-1,sDIM + sh,sDIM+1,... sn-1] 
provided sDIM + sh is bounded by LBOUND(ARRAY,DIM) and 
UBOUND(ARRAY,DIM), else BOUNDARY or 
BOUNDARY[s0,...sDIM-1,sDIM,...). 

Examples. 
(i) EOSHIFT(_V=[1,2,3,4,5,6],3) is [4,5,6,0,0,0]. 
EOSHIFT(_V,-2,99) is [99,99,1,2,3,4]. 
(ii) EOSHIFT(_M=[A B C],-1,'*',1) is [* A B]. 
[D E F] [* D E] 
[G H I] [* G H] 
EOSHIFT(_M,1,['*','/','?'],[-1,1,0]) is [* A B]. 
[E F /] 
[G H I]"""
    min_args=3
    max_args=4
    name='EOSHIFT'
    opcode=149

class FFT(NotSupported):
    """Transformation. Do a Finite Fourier Transform. 

Arguments Optional: DIM. 
ARRAY real or complex array. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 
S integer scalar for direction of the transform. 

Signals. Same as ARRAY with DIM-th dimension replaced by ramp. 
(Today, none.) 
Units... Same as ARRAY / DIM_OF(ARRAY,DIM)^2. (Today, none.) 
Form.... Complex array of same shape as X. 

Result.. Each element of ARRAY is replaced by the tranform using 
elements along dimension DIM. 
Example. ??"""
    min_args=2
    max_args=2
    name='FFT'
    opcode=163

class FIT(NotSupported):
    """Miscellaneous. Do a nonlinear least squares reduction of a function to 
zero given a starting guess. 

Arguments 
GUESS real vector of n elements. 
RESIDUALS an expression using variable name $X where the trial 
values are to appear. There are m residuals of the fit. 
Signals. Same as GUESS. 
Units... Same as GUESS. 
Form.... Same as GUESS. 

Result.. The best approximation to the value minimizing FCN*FCN. 

Example. The Rosenblock n=m=2 problem. 
FIT([-1.2,1.0],[10*($X[2]-$X[1]^2),1.0-$X[1]])."""
    min_args=2
    max_args=2
    name='FIT'
    opcode=165

class IBITS(NotSupported):
    """F90 Bit-wise Elemental. Extract a sequence of bits. ?? 

Arguments 
I integer. 
POS integer offset within the element of I. 
LEN integer length of bit field in I. F90 says POS + LEN 
must be less than or equal to BIT_SIZE(I). 

Signals. Same as I. 
Units... Same as I. 
Form.... Same type as I but no longer than LONG, compatible shape. 

Result.. The LEN bits starting at POS from beginning of I. 

Example. IBITS(14,1,3) is 7. 

See also. IBCLR to clear, IBSET to set, and BTEST to test. """
    min_args=3
    max_args=3
    name='IBITS'
    opcode=65

class INQUIRE(NotSupported):
    """F90 IO. ?? """
    min_args=2
    max_args=2
    name='INQUIRE'
    opcode=200

class INTEGRAL(NotSupported):
    """Transformation. Integrate along one dimension of an array. 

Arguments Optional: DIM, WIDTH. 
ARRAY numeric array. Signal uses dimension. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 
WIDTH real scalar. 

Signals. Same as ARRAY. 
Units... Same as for ARRAY*DIM_OF(ARRAY,DIM). (Today, ARRAY's.) 
Form.... Same as ARRAY. 

Result.. ??"""
    min_args=2
    max_args=3
    name='INTEGRAL'
    opcode=202

class INTERPOL(NotSupported):
    """Transformation. ??"""
    min_args=2
    max_args=3
    name='INTERPOL'
    opcode=203

class INTERSECT(NotSupported):
    """Miscellaneous. ??"""
    min_args=0
    max_args=254
    name='INTERSECT'
    opcode=204

class INVERSE(NotSupported):
    """Transformation. Matrix inversion. 

Argument. MATRIX must be a rank-2 array. 

Signals. Same as MATRIX. 
Units... Same as 1 / MATRIX. 
Form.... Same as MATRIX. 

Result.. ??"""
    min_args=1
    max_args=1
    name='INVERSE'
    opcode=206

class ISHFTC(NotSupported):
    """F90 Numeric Elemental. Circular left shift of rightmost bits. 

Arguments 
I must be integer. Octaword is not supported. 
SHIFT must be integer. The low byte is used. 
SIZE must be integer. The low byte is used. 

Signals. Single signal or smallest data. 
Units... Same as I. 
Form.... Type of I, compatible shape of all. 

Result.. The rightmost SIZE bits of I are shifted by SHIFT bits 
to the left with the highest bits filling the vacated 
bits. 

Example. ISHFTC(3,2,3) is 5."""
    min_args=3
    max_args=3
    name='ISHFTC'
    opcode=313

class ISQL(NotSupported):
    min_args=1
    max_args=1
    name='ISQL'
    opcode=416

class ISQL_SET(NotSupported):
    min_args=1
    max_args=3
    name='ISQL_SET'
    opcode=449

class IS_IN(NotSupported):
    """Logical Elemental. Test if element is in a set of elements. 
Usual Form X IS_IN SET. 

Arguments 
X numeric or character. 
SET numeric or character array. 

Signals. Same as X. 
Units... None. 
Form.... Logical of X shape. 

Result.. True for each element of X that is in SET; 
otherwise false. 

Example. 6 IS_IN [1..5,7] is $FALSE."""
    min_args=2
    max_args=3
    name='IS_IN'
    opcode=209

class LAMINATE(NotSupported):
    min_args=2
    max_args=254
    name='LAMINATE'
    opcode=213

class MATMUL(NotSupported):
    """F90 Transformation. Performs matrix multiplication of numeric matrices. 

Arguments 
MATRIX_A numeric array of rank one or two. A vector is 
considered to be of shape [1,m]. 
MATRIX_B numeric array of rank one or two. The size of the first 
dimension of MATRIX_B must be the same as the size of 
the last dimension of MATRIX_A. A vector is considered 
to be of shape [m,1]. 
There is no support for F90 logical arrays. 

Signals. Single signal or smaller data. 
Units... Same as for MATRIX_A * MATRIX_B. 
Form.... If MATRIX_A has shape [n,m] and MATRIX_B has shape 
[m,k], the result has shape [n,k]. For rank-one cases, 
the n or k is omitted. 

Result.. Result element [i,j] is 
SUM(MATRIX_A[i,:] * MATRIX_B[:,j]). 

Examples. MATMUL(_A=[1 2 3],_B=[1 2]) is [14 20]. 
[2 3 4] [2 3] [20 29] 
[3 4] 
MATMUL([1,2],_A) is vector-matrix product [5,8,11]. 
MATMUL(_A,[1,2,3]) is matrix-vector product [14,20]."""
    min_args=2
    max_args=2
    name='MATMUL'
    opcode=230

class MAT_ROT(NotSupported):
    """Transformation. Rotate a matrix about a point. 

Arguments 
MATRIX rank-two array. 
ANGLE real scalar, clockwise? rotation of the data. 
MAG real scalar, magnification. 
X0 real scalar, first axis center of rotation. 
Y0 real scalar, second axis center of rotation. 

Signals. Same as MATRIX. 
Units... Same as MATRIX. 
Form.... Same as MATRIX. 

Result.. The value at closest grid point to the rotated array. 

Example. ??"""
    min_args=2
    max_args=5
    name='MAT_ROT'
    opcode=231

class MAT_ROT_INT(NotSupported):
    """Transformation. Rotate a matrix about a point with interpolation. 

Arguments 
MATRIX rank-two array. 
ANGLE real scalar, clockwise? rotation of the data. 
MAG real scalar, magnification. 
X0 real scalar, first axis center of rotation. 
Y0 real scalar, second axis center of rotation. 

Signals. Same as MATRIX. 
Units... Same as MATRIX. 
Form.... Same as MATRIX. 

Result.. The value interpolated from near-by grid points to the 
rotated array. 

Example. ??"""
    min_args=2
    max_args=5
    name='MAT_ROT_INT'
    opcode=232

class MEDIAN(NotSupported):
    """Transformation. Median filter of specified width or area. 

Arguments 
ARRAY integer or real, vector or rank-two array. 
WIDTH integer scalar. 

Signals. Same as ARRAY. 
Units... Same as ARRAY. 
Form.... Same as ARRAY. 

Result.. Each element at least WIDTH/2 from the edge is median of 
the values WIDTH/2 on each side of it. The perimeter is 
equal to the first interior value. (subject to change) 

Example. ??"""
    min_args=2
    max_args=2
    name='MEDIAN'
    opcode=238

class MODULO(NotSupported):
    """F90 Numeric Elemental. Remainder. 
Usual Form A MODULO P. 

Arguments A and P must be integer or real. 
Complex numbers are an error. 

Signals. Single signal or smaller data. 
Units... Single or common units, else bad. 
Form.... Compatible form of A and P. 

Result.. If P NE 0, the result is A-FLOOR(REAL(A)/(REAL)P)*P. 
If P==0, the result is the $ROPRAND for reals and 
undefined for integers. 
Examples. MODULO(8,5) is 3. MODULO(-8,5) is 2. 
MODULO(8,-5) is -2. MODULO(-8,-5) is -3."""
    min_args=2
    max_args=2
    name='MODULO'
    opcode=412

class NEAREST(NotSupported):
    """F90 Numeric Elemental. Nearest different machine represntable number in 
a given direction. 

Arguments 
X real. 
S real and not zero. 

Signals. Single signal or smaller data. 
Units... Same as X. 
Form.... Same as X. 

Result.. The machine representable number distinct from X and 
nearest to it in the direction to the infinity of the 
same sign as S. 

Example. NEAREST(3.0,2.0) is 3+2^(-22)."""
    min_args=2
    max_args=2
    name='NEAREST'
    opcode=253

class ON_ERROR(NotSupported):
    """Miscellaneous. On an error do the action A. 

Argument. Optional: A. 
A may be any expression. The default is to cancel previous 
setting. 

Result.. The result of action A. 
Example. ?? if ever."""
    min_args=1
    max_args=1
    name='ON_ERROR'
    opcode=262

class PROJECT(NotSupported):
    """Transformation. Select masked values from an array. 

Arguments Optional: DIM. 
ARRAY any type array. 
MASK logical array of same shape as ARRAY, must have at most 
one true value. 
FIELD same type as ARRAY. Scalar if no DIM, else rank n-1 with 
same shape as ARRAY except that dimension DIM is 
omitted. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 

Signals. Single signal or smallest of ARRAY or MASK. 
Units... Single or common value of ARRAY or FIELD. 
Form.... Type of ARRAY. Scalar if DIM is absent or ARRAY is a 
vector, else rank n-1 and shape like ARRAY without 
dimension DIM. 

Result. 
(i) Without DIM, the element of ARRAY corresponding to the 
one true element of MASK. If no true elements, uses 
FIELD. 
(ii) With DIM, the resultant element is taken form ARRAY 
element along the dimension DIM with FIELD omitting 
subscript DIM. 

Examples. 
(i) _V=[1,2,3,4] and _P=[0,0,1,0], then 
PROJECT(_V,_P,0) is 3. 
PROJECT(_V,_V GT 5,99) is 3. 
(ii) If _A=[1 4 7 10] and _L=[0 0 0 0], then 
[2 5 8 11] [0 0 1 0] 
[3 6 9 12] [0 0 0 0] 
PROJECT(_A,_L,0) is 8. 
PROJECT(_A,_L,[0,0,0],1) is [0,8,0], and 
PROJECT(_A,_L,[0,0,0,0],0) is [0,0,8,0]. 
[0 2 0 0] 
[0 3 5 0] 
[1 4 6 0] 
If _M=[0 0 0 0], then 
PROJECT(_M,FIRSTLOC(_M NE 0,0),[-1,-1,-1,-1],0) is 
[1,2,5,-1]."""
    min_args=3
    max_args=4
    name='PROJECT'
    opcode=282

class PROMOTE(NotSupported):
    """Transformation. Add a dimension, repeating the values. 
Usual Form NCOPIES @ VALUE. 
Function Form promote(NCOPIES,VALUE) 

Arguments 
NCOPIES integer scalar or vector. 
VALUE any type, scalar or array. 
Signals. Same as VALUE with highest dimension increased. (?) 
Units... Same as VALUE. 
Form.... The VALUE's type with more dimension(s). 

Result.. NCOPIES of VALUE will be place end to end. 

Example. [1,3]@[5,4] is [5,4, 5,4, 5,4] with shape [2,1,3]. 
See also REPLICATE and SPREAD."""
    min_args=2
    max_args=2
    name='PROMOTE'
    opcode=283

class RANDOM_SEED(NotSupported):
    """F90 Modified Miscellaneous. Initializes or restarts the pseudorandom 
number generator. 

Argument. Optional: PUT. 
PUT integer array to set seed value. 

Result.. Previous value of the seed. 
Example. ??"""
    min_args=0
    max_args=1
    name='RANDOM_SEED'
    opcode=291

class RC_DROOP(NotSupported):
    """Transformation. Correct for integrator droop along one dimension. 

Arguments Optional: DIM. 
ARRAY real array. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 
RC real scalar. 

Signals. Same as ARRAY. 
Units... Same as ARRAY. 
Form.... Same as ARRAY. 

Result.. The droop-corrected array. The correction formula is 
X += integral from time=0 to t of X(t)*dt/RC, 
where t is dimension DIM and X is the value along it. 

Example. ??"""
    min_args=3
    max_args=3
    name='RC_DROOP'
    opcode=375

class READ(NotSupported):
    """IO. Input from a file.?? """
    min_args=1
    max_args=1
    name='READ'
    opcode=295

class REBIN(NotSupported):
    """Transformation. Linearly expands or shrinks array. 

Arguments 
ARRAY vector or matrix. 
SIZE1 integer scalar. 
SIZE2 integer scalar, required for matrix, absent for vector. 

Signals. Same as ARRAY. 
Units... Same as ARRAY. 
Form.... Vector of SIZE1 elements or 
MATRIX of shape [SIZE1,SIZE2]. 

Result.. Linearly or bi-linearly interpolated values. 

Example. ??"""
    min_args=2
    max_args=4
    name='REBIN'
    opcode=297

class RESHAPE(NotSupported):
    """F90 Transformation. Change the shape of an array. 

Arguments Optional: PAD, ORDER. 
SOURCE any type, if PAD absent or size zero then its size must 
be at least PRODUCT(SHAPE). 
SHAPE integer vector of not more than 8 non-negative elements 
PAD same type as SOURCE 
ORDER integer of same shape as SHAPE and must be a permutation 
of [0:n-1], where n is the size of SHAPE. 
Default is [0:n-1]. 

Signals. Same as SOURCE. 
Units... Single or common units of SOURCE and PAD. 
Form.... An array of shape SHAPE with the type of SOURCE. 

Result.. The elements are those of SOURCE followed by additional 
copies of PAD to fill the size. The indexes are permuted 
by ORDER. 

Example. RESHAPE([1:6],[2,3]) is [1 3 5]. 
[2 4 6]"""
    min_args=2
    max_args=4
    name='RESHAPE'
    opcode=301

class REWIND(NotSupported):
    """F90 IO. Set file pointer to initial record.??"""
    min_args=1
    max_args=1
    name='REWIND'
    opcode=303

class RMS(NotSupported):
    """Transformation. Root mean sum of the elements of ARRAY along dimension 
DIM corresponding to the true elements of MASK. The rms 
value is the square root of the mean of the squares of 
the elements. 

Arguments Optional: DIM, MASK. 
ARRAY floating point array. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 
MASK logical and conformable to ARRAY. 

Signals. Same as ARRAY if DIM-th or all dimensions omitted. 
Units... Same as ARRAY. 
Form.... Same type as ARRAY. It is a scalar if DIM is absent or 
ARRAY is scalar or vector. Otherwise, the result is an 
array of rank n-1 and shaped like ARRAY with DIM 
subscript omitted. 

Result.. The result without DIM is the rms value of the elements 
of ARRAY, testing only those with true MASK values and 
value not equal to the reserved operand ($ROPRAND). With 
DIM, the value of an element of the result is rms of the 
ARRAY elements with dimension DIM fixed as the element 
number of the result. If no value is found, 0 is given. 

Examples. RMS([1,2,3]) is sqrt(13/3.). RMS(_C,,_C GT 0) finds the 
rms of positive element of C. If _B=[1 3 5], 
[2 4 6] 
RMS(_B,0) is sqrt([5,25,61]/2.) and 
RMS(_B,1) is sqrt([35,56]/3.)."""
    min_args=1
    max_args=3
    name='RMS'
    opcode=304

class SIGN(NotSupported):
    """F90 Numeric Elemental. The magnitude of A with the sign of B. 

Arguments A and B must be integer or real. 
Complex numbers are an error. 

Signals. Single signal or smaller data. 
Units... Same as A. 
Form.... Type of A, compatible shape of all. 

Result.. ABS(A) if B>=0 and -ABS(A) if B<0. 

Example. SIGN(-3.0,2.0) is 3.0."""
    min_args=2
    max_args=2
    name='SIGN'
    opcode=316

class SMOOTH(NotSupported):
    """Transformation. Rectangular average along a dimension. 

Arguments Optional: DIM. 
ARRAY numeric. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 
WIDTH integer scalar. 

Signals. Same as ARRAY. 
Units... Same as ARRAY. 
Form.... Same as ARRAY. 

Result.. The average of element along dimension DIM from WIDTH/2 
before to WIDTH/2 afterward. 

Example. ??"""
    min_args=2
    max_args=2
    name='SMOOTH'
    opcode=323

class SOLVE(NotSupported):
    """Miscellaneous. Solve linear equations: MATMUL(MATRIX,X)=VECTOR. 

Arguments 
VECTOR real or complex vector of n elements. 
ARRAY real or complex array of shape [n,n]. 

Signals. Same as VECTOR. 
Units... Same as INVERSE(MATRIX) * VECTOR. 
Form.... Vector of compatible type of VECTOR and ARRAY. 

Result.. Equivalent to MATMUL(INVERSE(MATRIX),VECTOR). 

Example. SOLVE([3,4],SET_RANGE(2,2,[1,2,2,5])) is [7.0,-2.0]."""
    min_args=2
    max_args=2
    name='SOLVE'
    opcode=324

class STD_DEV(NotSupported):
    """Transformation. Standard deviation of the elements of ARRAY along 
dimension DIM corresponding to the true elements of 
MASK. The std_dev value is the square root of the sum of 
squares of the difference from the average of the 
elements divided by one less than the number of entries. 

Arguments Optional: DIM, MASK. 
ARRAY floating point array. 
DIM integer scalar from 0 to n-1, where n is rank of ARRAY. 
MASK logical and conformable to ARRAY. 

Signals. Same as ARRAY if DIM-th or all dimensions omitted. 
Units... Same as ARRAY. 
Form.... Same type as ARRAY. It is a scalar if DIM is absent or 
ARRAY is scalar or vector. Otherwise, the result is an 
array of rank n-1 and shaped like ARRAY with DIM 
subscript omitted. 

Result.. The result without DIM is the std_dev value of the 
elements of ARRAY, testing only those with true MASK 
values and value not equal to $ROPRAND. With DIM, the 
value of an element of the result is std_dev of the 
ARRAY elements with DIM dimension fixed as the element 
number of the result. If no value is found, zero is 
returned. 

Examples. STD_DEV([1,2,3]) is SQRT(2./2). STD_DEV(_C,,_C GT 0) 
finds the std_dev of positive element of C. 
If _B=[1 3 5], STD_DEV(_B,0) is SQRT([1.,1.,1.]/1) and 
[2 4 6] 
STD_DEV(_B,1) is SQRT([4.,4.]/2)."""
    min_args=1
    max_args=3
    name='STD_DEV'
    opcode=332

class STRING(NotSupported):
    """Transformation. Converts data to a text string. 

Arguments Optional: Y, FORMAT. 
X any type that can be converted to character. 
Y,... more arguments. If present, FORMAT must be present. 
FORMAT character scalar to control the conversion. 

Signals. None. 
Units... None. 
Form.... Character scalar. 

Result.. ?? 

Example. ??"""
    min_args=1
    max_args=254
    name='STRING'
    opcode=333

class SYSTEM_CLOCK(NotSupported):
    """F90 Modified IO. Integer data from the real-time clock. ?? 

Argument. STRING is character scalar. One of the strings COUNT, 
COUNT_RATE, or COUNT_MAX. 

Signals. Same as STRING. 
Units... None, bad if STRING has units. 
Form.... Integer scalar. 

Result.. Depends on the time of day. 

Example. If the basic system clock registers time in 0.01 second 
intervals, at 11:30 then on a VAX: 
SYSTEM_CLOCK("COUNT") is ((11*60+30)*60)/0.01=4140000, 
SYSTEM_CLOCK("COUNT_RATE") is 100, 
SYSTEM_CLOCK("COUNT_MAX") is 24*60*60/0.01-1=8639999."""
    min_args=1
    max_args=1
    name='SYSTEM_CLOCK'
    opcode=339

class TRANSFER(NotSupported):
    """F90 Transformation. A result with a physical representation identical 
to that of SOURCE but interpreted with the type of MOLD. 

Arguments Optional: SIZE. 
SOURCE any type, scalar or array. 
MOLD any type, scalar or array. 
SIZE integer scalar. 

Signals. Same as SOURCE. 
Units... Single or common units of SOURCE and MOLD, else bad. 
Form.... The type of MOLD, scalar if MOLD is scalar and SIZE is 
absent. If MOLD is an array and SIZE is absent, the 
result is a vector and the size is as small as possible 
such that its physical representation is not shorter 
than that of source. If SIZE present, the result is a 
vector and the size is SIZE. 

Result.. If the physical representation of the result is as long 
as length as that of SOURCE, the physical representation 
of the result is that of SOURCE and the remainder is 
undefined; otherwise, the result is the leading part of 
SOURCE. 

Examples. TRANSFER(0x4180,0.0) is 4.0 on the VAX. 
TRANSFER([1.1,2.2,3.3],[CMPLX(0.0,0.0)]) is a complex 
vector of length 2 whose first element is CMPLX(1.1,2.2) 
and whose second element has real part 3.3. 
TRANSFER([1.1,2.2,3.3],[CMPLX(0.0,0.0)],1) is 
[CMPLX(1.1,2.2)]."""
    min_args=2
    max_args=3
    name='TRANSFER'
    opcode=347

class TRANSPOSE_(NotSupported):
    """F90 Transformation. Transpose an array of rank two. 

Argument. MATRIX is any type, rank-2 array. 

Signals. Same as MATRIX with dimensions exchanged. 
Units... Same as MATRIX. 
Form.... Same type as MATRIX with the indices interchanged. 

Result.. Element [i,j] of the result is MATRIX[j,i] for all 
i and j in the extent of the dimensions. 

Example. TRANSPOSE([1 2 3]) is [1 4 7]. 
[4 5 6] [2 5 8] 
[7 8 9] [3 6 9] """
    min_args=1
    max_args=1
    name='TRANSPOSE_'
    opcode=348

class TRANSPOSE_MUL(NotSupported):
    """Transformation. Performs matrix multiplication of numeric matrices, 
transposing the first. 

Arguments 
MATRIX_A numeric array of rank one or two. 
MATRIX_B numeric array of rank one or two. The size of the first 
dimension of MATRIX_B must be the same as the size of 
the last dimension of MATRIX_A. 

Signals. Single signal or smaller data. 
Units... Same as for MATRIX_A * MATRIX_B. 
Form.... If MATRIX_A has shape [m,n] and MATRIX_B has shape 
[m,k], the result has shape [n,k]. For rank-one cases, 
the n or k is omitted. 

Result.. Result element [i,j] is 
SUM(MATRIX_A[:,i] * MATRIX_B[:,j]). 

Examples. TRANSPOSE_MUL(_A=[1 2],_B=[1 2]) is [14 20]. 
[2 3] [2 3] [20 29] 
[3 4] [3 4] 
TRANSPOSE_MUL([1,2],_A) is vector-matrix product 
[5,8,11]. 
TRANSPOSE_MUL(_A,[1,2,3]) is matrix-vector product 
[14,20]."""
    min_args=2
    max_args=2
    name='TRANSPOSE_MUL'
    opcode=382

class UNPACK(NotSupported):
    """F90 Transformation. Unpack an array into an array under control of a 
mask. 

Arguments 
VECTOR any type. Its size must be at least equal to the number 
of $TRUE elements of MASK. 
MASK logical array. 
FIELD same type as VECTOR and conformable with MASK. 
Signals. Single signal or smaller data. 
Units... Single or common units of VECTOR and FIELD, else bad. 
Form.... The type of VECTOR and the shape of MASK. 

Result.. That corresponding to j-th true element of MASK in array 
element order, is VECTOR(j-1). Other elements have value 
equal to the corresponding element of FIELD. 

Examples. Specific values may be scattered to specific positions. 
UNPACK(_v=[1,2,3],_q=[0 1 0],[0 0 0],[0 1 0]) is [1 2 0]) 
[1 0 0] [0 0 0] [1 0 0] [1 1 0] 
[0 0 1] [0 0 0] [0 0 1] [0 0 3] 
and UNPACK(_v,_q,0) is [0 2 0]. 
[1 0 0] 
[0 0 3]"""
    min_args=3
    max_args=3
    name='UNPACK'
    opcode=355

class WHERE(NotSupported):
    """F90 Statement. Do statement if expression true, else possibly do 
another. Unsubscripted variables that would be replaced 
and that are of matching size have only the true 
elements replaced/calculated. 
Required Usual Forms. WHERE (TEST) STMT, 
WHERE (TEST) STMT ELSEWHERE ELSESTMT. 
Function Form where(TEST,STMT,[ELSESTMT]). 
May be syntatically invalid. 

Arguments Optional: ELSESTMT. 
TEST logical array, this is an "array IF". 
STMT statement. 
ELSESTMT statement. 

Result.. None. 

Example. WHERE (_A > 0) _A += 6; ELSEWHERE _A -= 6;."""
    min_args=2
    max_args=3
    name='WHERE'
    opcode=365
