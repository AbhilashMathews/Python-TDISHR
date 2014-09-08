"""
MDSplus tests
==========

Tests of MDSplus

"""
from unittest import TestCase,TestSuite,TextTestRunner,TestResult

if '__package__' not in globals() or __package__ is None or len(__package__)==0:
  def _mimport(name,level):
    try:
      return __import__(name,globals())
    except:
      return __import__('MDSplus.'+name,globals())
else:
  def _mimport(name,level):
    try:
      return __import__(name,globals(),{},[],level)
    except ValueError:
      return __import__(name,globals())

_treeUnitTest=_mimport('treeUnitTest',1)
_threadsUnitTest=_mimport('threadsUnitTest',1)
_dataUnitTest=_mimport('dataUnitTest',1)
_data=_mimport('data',2)

import os
import time
import warnings

class cleanup(TestCase):
    dir=None

    def cleanup(self):
        if cleanup.dir is not None:
            dir=cleanup.dir
            for i in os.walk(dir,False):
                for f in i[2]:
                    try:
                      os.remove(i[0]+os.sep+f)
                    except Exception:
                      import sys
                      e=sys.exc_info()[1]
                      print( e)
                for d in i[1]:
                    try:
                      os.rmdir(i[0]+os.sep+d)
                    except Exception:
                      import sys
                      e=sys.exc_info()[1]
                      print( e)
            try:
              os.rmdir(dir)
            except Exception:
              import sys
              e=sys.exc_info()[1]
              print( e)
        return
    def runTest(self):
        self.cleanup()

def test_all(*arg):
    import tempfile
    dir=tempfile.mkdtemp()
    print ("Creating trees in %s" % (dir,))
    cleanup.dir=dir
    if (str(_data.Data.execute('getenv("TEST_DISTRIBUTED_TREES")')) == ""):
        hostpart=""
    else:
        hostpart="localhost::" 
    _data.Data.execute('setenv("pytree_path='+hostpart+dir.replace('\\','\\\\')+'")')
    _data.Data.execute('setenv("pytreesub_path='+hostpart+dir.replace('\\','\\\\')+'")')
    print (_data.Data.execute('getenv("pytree_path")'))
    tests=list()
    tests.append(_treeUnitTest.treeTests())
    if os.getenv('TEST_THREADS') is not None:
        tests.append(_threadsUnitTest.suite())
    tests.append(_dataUnitTest.suite())
    tests.append(TestSuite([cleanup('cleanup')]))
    return TestSuite(tests)

