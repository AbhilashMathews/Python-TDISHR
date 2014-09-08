"""
MDSplus
==========

Provides a object oriented interface to the MDSplus data system.

Information about the B{I{MDSplus Data System}} can be found at U{the MDSplus Homepage<http://www.mdsplus.org>}
@authors: Tom Fredian(MIT/USA), Gabriele Manduchi(CNR/IT), Josh Stillerman(MIT/USA)
@copyright: 2008
@license: GNU GPL



"""
if '__package__' not in globals() or __package__ is None or len(__package__)==0:
  def _mimport(name,level):
    return __import__(name,globals())
else:
  def _mimport(name,level):
    return __import__(name,globals(),{},[],level)

def _loadModule(name,level,glob):
  """Load all the objects in a module which do not begin with underscore.
  This is essentially the equivalent of doing:
     from module import *
  but should work in python version 2.4 through 3.x"""
  module=_mimport(name,level)
  for key in module.__dict__.keys():
    if not key.startswith('_'):
      glob[key]=module.__dict__[key]

_loadModule('data',1,globals())
_loadModule('tree',1,globals())
_loadModule('event',1,globals())
_loadModule('connection',1,globals())
_loadModule('scope',1,globals())
_loadModule('tdipy',1,globals())

