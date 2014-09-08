"""The builtin package provides all the objects used in implementing the TDI (Tree Data Interface)
expression evaluator. TDI expression syntax is compiled into builtin objects or MDSplus scalars or arrays or
compound objects such as signals, ranges, dimentions etc...

The builtins included in MDSplus are listed below:

"""
import os as _os
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

def loadBuiltins(module):
    for item in dict(module.__dict__).values():
        try:
            if issubclass(item,Builtin):
                globals()[item.name]=item
                if item.name.startswith('$'):
                  globals()['d'+item.name[1:]]=item
        except:
            pass

#_builtin=_mimport('builtin',1)
#Builtin=_builtin.Builtin
_builtin_set=_mimport('builtin_set',1)
Builtin=_builtin_set.Builtin

loadBuiltins(_builtin_set)

Builtin.loadBuiltins(globals())

def _addDocs(__doc__):
    total=0
    total_python=0
    keys=list(Builtin.builtins_by_name.keys())
    keys.sort()
    for key in keys:
        b=Builtin.builtins_by_name[key]
        d=b.getDoc()
        if d is not None:
            total=total+1
            if "Native python:   True" in d:
                total_python=total_python+1
            __doc__=__doc__+d+'\n\n'
    __doc__=__doc__+"Total of %d builtins of which %d are implemented in Python\n" % (total,total_python)
    return __doc__

__doc__=_addDocs(__doc__)

def _CCODE_GEN(filename):
    f=open(filename,'w')
    f.write("""#include <mdsdescrip.h>
#include <mds_stdarg.h>
#include <tdimessages.h>

extern EvaluateBuiltin(const int opcode, const char *builtin_name, int nargs, struct descriptor **args);

""")
    keys = Builtin.builtins_by_name.keys()
    keys.sort()
    for key in keys:
        b=Builtin.builtins_by_name[key]
        f.write("unsigned short Opc%s = %d;\n" % (b.getCCodeName(),b.opcode))
        glue=b.getCCodeGlue()
        if glue is not None:
            f.write(glue)
            f.write("\n\n")
    f.close()
