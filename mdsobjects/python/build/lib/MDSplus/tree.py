import ctypes as _C
import numpy as _NP
import threading as _threading
import sys as _sys
import traceback as _traceback

if '__package__' not in globals() or __package__ is None or len(__package__)==0:
  def _mimport(name,level):
    return __import__(name,globals())
else:
  def _mimport(name,level):
    return __import__(name,globals(),{},[],level)

_thread_data=_threading.local()
_data=_mimport('data',1)

_TreeShr=_data._loadLib('TreeShr')
_TreeSwitchDbid=_TreeShr.TreeSwitchDbid
_TreeSwitchDbid.argtypes=[_C.c_void_p]
_TreeSwitchDbid.restype=_C.c_void_p

_usageTable={'ANY':0,'NONE':1,'STRUCTURE':1,'ACTION':2,'DEVICE':3,'DISPATCH':4,'NUMERIC':5,'SIGNAL':6,
             'TASK':7,'TEXT':8,'WINDOW':9,'AXIS':10,'SUBTREE':11,'COMPOUND_DATA':12,'SUBTREE':-1}

class TreeException(Exception):
  pass

class TreeNoDataException(Exception):
  pass

class Tree(object):
    """Open an MDSplus Data Storage Hierarchy"""

    _lock=_threading.RLock()
    _activeTree=None

    class _DBI_ITM_INT(_C.Structure):
      _fields_=[("buffer_length",_C.c_ushort),("code",_C.c_ushort),("pointer",_C.POINTER(_C.c_int32)),
                ("retlen",_C.c_void_p),
                ("buffer_length2",_C.c_ushort),("code2",_C.c_ushort),("pointer2",_C.c_void_p),
                ("retlen2",_C.c_void_p),]
      def __init__(self,code,value):
        self.buffer_length=_C.c_ushort(4)
        self.code=_C.c_ushort(code)
        self.pointer=_C.pointer(value)
        self.retlen=_C.c_void_p(0)
        self.buffer_length2=0
        self.code2=0
        self.pointer2=_C.c_void_p(0)
        self.retlen2=_C.c_void_p(0)

    class _DBI_ITM_CHAR(_C.Structure):
      _fields_=[("buffer_length",_C.c_ushort),("code",_C.c_ushort),("pointer",_C.c_char_p),
                ("retlen",_C.POINTER(_C.c_int32)),
                ("buffer_length2",_C.c_ushort),("code2",_C.c_ushort),("pointer2",_C.c_void_p),
                ("retlen2",_C.c_void_p),]
        
      def __init__(self,code,buflen,string_p,retlen_p):
        self.buffer_length=_C.c_ushort(buflen)
        self.code=_C.c_ushort(code)
        self.pointer=string_p
        self.retlen=_C.pointer(retlen_p)
        self.buffer_length2=0
        self.code2=0
        self.pointer2=_C.c_void_p(0)
        self.retlen2=_C.c_void_p(0)
        
    def __del__(self):
      """Delete Tree instance
      @rtype: None
      """
      self.close()

    def close(self):
      """Close the the connection to the tree"""
      if self.ctx is not None:
        while (_TreeShr._TreeClose(_C.pointer(self.ctx),_C.c_void_p(0),_C.c_int32(0)) & 1)==1:
          pass
      if Tree.getActiveTree() == self:
        Tree.setActiveTree(None)
        _TreeSwitchDbid(_C.c_void_p(0))
      _TreeShr.TreeFreeDbid(self.ctx)
      self.ctx=None
      

    def __getattr__(self,name_in):
        """
        Implements value=tree.attribute

        Attributes defined:

         - default - TreeNode, Current default node
         - modified - bool, True if tree structure has been modified
         - name - str, Tree name
         - open_for_edit - bool, True if tree open for edit
         - open_readonly - boo, True if tree was opened readonly
         - shot - int, Shot number
         - shotid - int, Shot number
         - tree - str, Tree name
         - versions_in_model - bool, True if versions enabled in the model
         - versions_in_pulse - bool, True if versions enabled in the pulse

        @param name: Name of attribute
        @type name: str
        @return: Value of attribute
        @rtype: various
        """
        name=name_in.lower()
        if name in ('ctx',):
          ans=self.__dict__[name]
        elif name == 'default':
          ans=self.getDefault()
        elif name == 'top':
          return TreeNode(0,self)
        else:
          if name == 'shot':
            name='shotid'
          elif name == 'tree':
            name='name'
          itemlist={'name':(1,str,12),'shotid':(2,int),'modified':(3,bool),
                    'open_for_edit':(4,bool),'index':(5,int),'number_opened':(6,int),
                    'max_open':(7,int),'default':(10,int),'open_readonly':(9,bool),
                    'versions_in_model':(10,bool),'versions_in_pulse':(11,bool)}
          if name in itemlist:
            item=itemlist[name]
            if item[1]==str:
              ans=_C.c_char_p(str.encode('x'.rjust(item[2])))
              retlen=_C.c_int32(0)
              itmlst=self._DBI_ITM_CHAR(item[0],item[2],ans,retlen)
            else:
              ans=_C.c_int32(0)
              itmlst=self._DBI_ITM_INT(item[0],ans)
            try:
              self.lock()
              status=_TreeShr._TreeGetDbi(self.ctx,_C.cast(
                  _C.pointer(itmlst),_C.c_void_p))
            finally:
              self.unlock()
            if not (status & 1):
              raise TreeException(_data.getStatusMsg(status))
            if item[1]==str:
              if isinstance(ans.value,str):
                ans = ans.value
              else:
                ans = ans.value.decode()
            else:
              ans = item[1](ans.value)
          elif name_in in self.__dict__:
            ans=self.__dict__[name_in]
          else:
            raise AttributeError("type object '%s' has no attribute '%s'" % (type(self).__name__,name_in))
        return ans

    def usePrivateCtx(cls,on=True):
        global _thread_data
        if not hasattr(_thread_data,"activeTree"):
            _thread_data.activeTree=None
        _thread_data.private=on
        _TreeShr.TreeUsePrivateCtx(_C.c_int32(on))
    usePrivateCtx=classmethod(usePrivateCtx)

    def __new__(kls, tree=None, shot=-1, mode='Normal'):
      if tree is None:
        ans = Tree.getActiveTree()
        if ans is None:
          ctx=_TreeSwitchDbid(_C.c_void_p(0))
          if ctx is not None:
            _TreeSwitchDbid(ctx)
            ans=super(Tree,kls).__new__(kls)
            ans.ctx=_C.c_void_p(ctx)
        return ans
      else:
        return super(Tree,kls).__new__(kls)

    def __init__(self, tree=None, shot=-1, mode='NORMAL'):
      """Create a Tree instance. Specify a tree and shot and optionally a mode.
      If providing the mode argument it should be one of the following strings:
      'Normal','Edit','New','ReadOnly'.
      If no arguments provided, create instance of the active tree. (i.e. Tree())
      @param tree: Name of tree to open
      @type tree: str
      @param shot: Shot number
      @type shot: int
      @param mode: Optional mode, one of 'Normal','Edit','New','Readonly'
      @type mode: str
      """
      def _open(self,tree,shot,mode):
        """Open the tree. Separate function for profiling"""
        self.ctx=_C.c_void_p(0)
        mode=mode.upper()
        if mode in ('NORMAL','EDIT'):
          status = _TreeShr._TreeOpen(_C.pointer(self.ctx),
                                      _C.c_char_p(str.encode(tree)),_C.c_int32(shot),_C.c_int32(0))
          if ((status & 1)==1)and (mode == 'EDIT'):
            Tree.lock()
            status = _TreeShr._TreeOpenEdit(_C.pointer(self.ctx),_C.c_char_p(str.encode(tree)),_C.c_int32(shot))
            Tree.unlock()
        elif mode.upper() == 'NEW':
          status = _TreeShr._TreeOpenNew(_C.pointer(self.ctx),
                                         _C.c_char_p(str.encode(tree)),_C.c_int32(shot))
        elif mode.upper() == 'READONLY':
          status = _TreeShr._TreeOpen(_C.pointer(self.ctx),
                                      _C.c_char_p(str.encode(tree)),_C.c_int32(shot),_C.c_int32(1))
        else:
          raise TreeException('Invalid mode specificed, use "Normal","Edit","New" or "ReadOnly".')
        if (status & 1)==0:
          raise TreeException('Error opening tree: %s, shot: %d, error: %s' % (tree,shot,_data.getStatusMsg(status)))
        Tree.setActiveTree(self)

      if tree is not None:
        _open(self,tree,shot,mode)

    def __deepcopy__(self,memo):
        return self

    def __setattr__(self,name_in,value):
        """
        Implements tree.attribute=value

        Attributes defined:

         - default - TreeNode, default node in tree
         - versions_in_model - bool, True to enable versions in model
         - versions_in_pulse - bool, True to enable versions in pulse

        @param name: Name of attribute to set
        @type name: str
        @param value: Value of attribute
        @type value: various
        @rtype: None
        """
        name=name_in.lower()
        if name in ('ctx'):
          self.__dict__[name]=value
        elif name in ('modified','name','open_for_edit','open_readonly','shot','shotid','tree'):
          raise AttributeError('Read only attribute: '+name)
        elif name == 'default':
          self.setDefault(value)
        else:
          itemlist={'versions_in_model':(10,bool),'versions_in_pulse':(11,bool)}
          if name in itemlist:
            item=itemlist[name]
            if item[1]==str:
              retlen=_C.c_int32(0)
              itmlst=self._DBI_ITM_CHAR(item[0],len(str(value)),_C.c_char_p(str(value)),retlen)
            else:
              ans=_C.c_int32(0)
              itmlst=self._DBI_ITM_INT(item[0],_C.c_int32(int(value)))
            try:
              tree.lock()
              status=_TreeShr._TreeSetDbi(tree.ctx,_C.cast(
                  _C.pointer(itmlst),_C.c_void_p))
            finally:
              tree.unlock()
            if not (status & 1):
              raise TreeException(_data.getStatusMsg(status))
          else:
            self.__dict__[name_in]=value

    def __str__(self):
        """Return string representation
        @return: String representation of open tree
        @rtype: str
        """
        if self.open_for_edit:
            mode="Edit"
        elif self.open_readonly:
            mode="Readonly"
        else:
            mode="Normal"
        return self.__class__.__name__+'("%s",%d,"%s")' % (self.tree,self.shot,mode)

    def addDevice(self,nodename,model):
        """Add a device to the tree of the specified device model type.
        @param nodename: Absolute or relative path specification of the head node of the device. All ancestors of node must exist.
        @type nodename: str
        @param model: Model name of the device being added.
        @type model: str
        @return: Head node of device added
        @rtype: TreeNode
        """
        try:
          Tree.lock()
          nid=_C.c_int32(0)
          status = _TreeShr._TreeAddConglom(self.ctx,
                                            _C.c_char_p(str.encode(str(nodename))),
                                            _C.c_char_p(str.encode(str(model))),_C.pointer(nid))
          if not (status & 1):
            raise TreeException("Error adding device node: %s, device %s, error: %s" % (nodename,model,
                                                                                          _data.getStatusMsg(status)))
        finally:
          Tree.unlock()
        return TreeNode(nid.value,self)

    def addNode(self,nodename,usage_in='ANY'):
        """Add a node to the tree. Tree must be in edit mode.
        @param nodename: Absolute or relative path specification of new node. All ancestors of node must exist.
        @type nodename: str
        @param usage: Usage of node.
        @type usage: str
        @return: Node created.
        @rtype: TreeNode
        """
        usage=usage_in.upper()
        if usage in _usageTable:
          subtree=False
          usage=_usageTable[usage]
          if usage==-1:
            subtree=True
            usage=1
          nid=_C.c_int32(0)
          Tree.lock()
          status = _TreeShr._TreeAddNode(self.ctx,_C.c_char_p(str.encode(str(nodename))),_C.pointer(nid),_C.c_int32(usage))
          if (status & 1)==1 and subtree:
            status = _TreeShr._TreeSetSubtree(self.ctx,nid)
          if (status & 1)==0:
            raise TreeException('Error adding node: %s, usage: %s, error: %s' % (nodename,usage_in,
                                                                                 _data.getStatusMsg(status)))
          Tree.unlock()
          return TreeNode(nid.value,self)
        else:
          raise TreeException('Invalid usage specified, must be on of: %s' % (str(_usageTable.keys()),))

    def createPulse(self,shot):
        """Create pulse.
        @param shot: Shot number to create
        @type shot: int
        @rtype: None
        """
        try:
          Tree.lock()
          try:
            subtrees=self.getNodeWild('***','subtree')
            included=subtrees.nid_number.compress(subtrees.include_in_pulse)
            included=included.toList()
            included.insert(0,0)
            included=_NP.array(included)
            status = _TreeShr._TreeCreatePulseFile(self.ctx,_C.c_int32(shot),_C.c_int32(len(included)),
                                                   _C.c_void_p(included.ctypes.data))
          except:
            status = _TreeShr._TreeCreatePulseFile(self.ctx,_C.c_int32(shot),_C.c_int32(0),_C.c_void_p(0))
          if (status & 1)==0:
            raise TreeException("Erro creating pulse: %s" % _data.getStatusMsg(status))
        finally:
            pass
            Tree.unlock()

    def deleteNode(self,wild):
        """Delete nodes (and all their descendants) from the tree. Note: If node is a member of a device,
        all nodes from that device are also deleted as well as any descendants that they might have.
        @param wild: Wildcard path speficier of nodes to delete from tree.
        @type wild: str
        @rtype: None
        """
        try:
          Tree.lock()
          first=True
          nodes=self.getNodeWild(wild)
          for node in nodes:
            count=_C.c_int32(0)
            reset=_C.c_int32(first)
            first=False
            status = _TreeShr._TreeDeleteNodeInitialize(self.ctx,_C.c_int32(node.nid),_C.pointer(count),reset)
            if (status & 1)==0:
              raise TreeException("Error deleting node(s): %s error:%s" % (wild,_data.getStatusMsg(status)))
          status = _TreeShr._TreeDeleteNodeExecute(self.ctx)
          if (status & 1)==0:
            raise TreeException("Error deleting node(s): %s error:%s" % (wild,_data.getStatusMsg(status)))
        finally:
            Tree.unlock()

    def deletePulse(self,shot):
        """Delete pulse.
        @param shot: Shot number to delete
        @type shot: int
        @rtype: None
        """
        try:
            Tree.lock()
            status = _TreeShr._TreeDeletePulseFile(self.ctx,_C.c_int32(shot),_C.c_int32(1))
            if (status & 1)==0:
              raise TreeException("Error deleting pulse %d, error: %s" (shot,_data.getStatusMsg(status)))
        finally:
            Tree.unlock()

    def doMethod(self,nid,method):
        """For internal use only. Support for PyDoMethod.fun used for python device support"""
        n=TreeNode(nid,self)
        top=n.conglomerate_nids[0]
        c=top.record
        q=c.qualifiers
        model=c.model

        for i in range(len(q)):
            exec( str(q[0]))
        try:
            exec( str('_data.makeData('+model+'(n).'+method+'(Data.getTdiVar("__do_method_arg__"))).setTdiVar("_result")'))
            _data.makeData(1).setTdiVar("_method_status")           
        except AttributeError:
            _data.makeData(0xfd180b0).setTdiVar("_method_status")
        except Exception:
            print("Error doing %s on node %s" % (str(method),str(n)))
            _data.makeData(0).setTdiVar("_method_status")
            raise
        return Data.getTdiVar("_result")

    def findTagsIter(self, wild):
        """An iterator for the tagnames from a tree given a wildcard specification.
        @param wild: wildcard spec.
        @type name: str
        @return: iterator of tagnames (strings) that match the wildcard specification
        @rtype: iterator
        """
        nid=_C.c_int32(0)
        ctx=_C.c_void_p(0)
        TreeFindTagWild=_TreeShr._TreeFindTagWild
        TreeFindTagWild.restype=_C.c_char_p
        try:
          while True:
            tag=TreeFindTagWild(self.ctx,_C.c_char_p(str.encode(wild)),_C.pointer(nid),_C.pointer(ctx))
            if tag:
              yield tag.rstrip()
            else:
              raise GeneratorExit()
        except GeneratorExit:
          pass
        _TreeShr.TreeFindTagEnd(_C.pointer(ctx))

    def findTags(self,wild):
        """Find tags matching wildcard expression
        @param wild: wildcard string to match tagnames.
        @type wild: str
        @return: Array of tag names matching wildcard expression
        @rtype: ndarray
        """
        return tuple(self.findTagsIter(wild))

    def getActiveTree():
        """Get active tree.
        @return: Current active tree
        @rtype: Tree
        """
        global _thread_data
        if not hasattr(_thread_data,"activeTree"):
            _thread_data.activeTree=None
            _thread_data.private=False
        if _thread_data.private:
          return _thread_data.activeTree
        else:
          return Tree._activeTree
    getActiveTree=staticmethod(getActiveTree)
    
    def getCurrent(treename):
        """Return current shot for specificed treename
        @param treename: Name of tree
        @type treename: str
        @return: Current shot number for the specified tree
        @rtype: int
        """
        try:
            Tree.lock()
            shot=_TreeShr.TreeGetCurrentShotId(_C.c_char_p(str.encode(treename)))
        finally:
            Tree.unlock()
        if shot==0:
            raise TreeException("Error obtaining current shot of %s" % (treename,))
        return shot
    getCurrent=staticmethod(getCurrent)

    def getDefault(self):
        """Return current default TreeNode
        @return: Current default node
        @rtype: TreeNode
        """
        try:
            Tree.lock()
            ans=_C.c_int32(0)
            status = _TreeShr._TreeGetDefaultNid(self.ctx,_C.pointer(ans))
            if (status & 1) == 0:
              raise TreeException("Error getting current default, error: %s",_data.getStatusMsg(status))
            ans = TreeNode(ans.value,self)
        finally:
            Tree.unlock()
        return ans
            
    def getNode(self,name):
        """Locate node in tree. Returns TreeNode if found. Use double backslashes in node names.
        @param name: Name of node. Absolute or relative path. No wildcards.
        @type name: str
        @return: Node if found
        @rtype: TreeNode
        """
        if isinstance(name,int):
            return TreeNode(name,self)
        else:
            try:
                Tree.lock()
                nid=_C.c_int32(0)
                status = _TreeShr._TreeFindNode(self.ctx,_C.c_char_p(str.encode(name)),_C.pointer(nid))
                if (status & 1)==1:
                  ans=TreeNode(nid.value,self)
                else:
                  raise TreeException('Error finding node: %s, error: %s' % (name,_data.getStatusMsg(status)))
            finally:
                Tree.unlock()
            return ans
        
    def getNodeWildIter(self, name, *usage):
        """An iterator for the nodes in a tree given a wildcard specification.
        @param name: Node name. May include wildcards.
        @type name: str
        @param usage: Optional list of node usages (i.e. "Numeric","Signal",...). Reduces return set by including only nodes with these usages.
        @type usage: str
        @return: iterator of TreeNodes that match the wildcard and usage specifications
        @rtype: iterator
        """
        FindNodeWild=_TreeShr._TreeFindNodeWild
        if len(usage) == 0:
          usage_mask=0xFFFF
        else:
          try:
            usage_mask=0
            for u in usage:
              usage_mask |= (1 << _usageTable[u.upper()])
          except KeyError:
            raise TreeException('Invalid usage %s specified, must be one of %s' % (u,str(_usageTable.keys())))
        nid=_C.c_int32()
        ctx=_C.c_void_p(0)
        while (FindNodeWild(self.ctx,str.encode(name),_C.pointer(nid),_C.pointer(ctx),_C.c_int32(usage_mask)) & 1) == 1:
            yield TreeNode(nid.value,self)
        _TreeShr.TreeFindNodeEnd(_C.pointer(ctx))

    def getNodeWild(self,name,*usage):
        """Find nodes in tree using a wildcard specification. Returns TreeNodeArray if nodes found.
        @param name: Node name. May include wildcards.
        @type name: str
        @param usage: Optional list of node usages (i.e. "Numeric","Signal",...). Reduces return set by including only nodes with these usages.
        @type usage: str
        @return: TreeNodeArray of nodes matching the wildcard path specification and usage types.
        @rtype: TreeNodeArray
        """
        nids=list()
        for n in self.getNodeWildIter(name,*usage):
            nids.append(n.nid)
        return TreeNodeArray(nids,self)

    def getVersionDate():
        """Get date used for retrieving versions
        @return: Reference date for retrieving data is versions enabled
        @rtype: str
        """
        dt=_C.c_ulonglong(0)
        status = _TreeShr.TreeGetViewDate(_C.pointer(dt))
        if (status & 1)==0:
          raise TreeException(_data.getStatusMsg(status))
        return _data.Uint64(dt.value).date
    getVersionDate=staticmethod(getVersionDate)

    def isModified(self):
        """Check to see if tree is open for edit and has been modified
        @return: True if tree structure has been modified.
        @rtype: bool
        """
        return self.modified

    def isOpenForEdit(self):
        """Check to see if tree is open for edit
        @return: True if tree is open for edit
        @rtype: bool
        """
        return self.open_for_edit

    def isReadOnly(self):
        """Check to see if tree was opened readonly
        @return: True if tree is open readonly
        @rtype: bool
        """
        return self.open_readonly

    def lock(cls):
        """Internal use only. Thread synchronization locking.
        """
        if not _TreeShr.TreeUsingPrivateCtx():
            cls._lock.acquire()
    lock=classmethod(lock)

    def quit(self):
        """Close edit session discarding node structure and tag changes.
        @rtype: None
        """
        try:
            Tree.lock()
            TreeQuitTree(self)
        finally:
            Tree.unlock()

    def removeTag(self,tag):
        """Remove a tagname from the tree
        @param tag: Tagname to remove.
        @type tag: str
        @rtype: None
        """
        TreeRemoveTag(self,tag)


    def _setActiveTree(tree):
        global _thread_data
        if not hasattr(_thread_data,"activeTree"):
            _thread_data.activeTree=None
            _thread_data.private=False
        if _thread_data.private:
          old = _thread_data.activeTree
          _thread_data.activeTree=tree
        else:
          old=Tree._activeTree
          Tree._activeTree=tree
        return old
    _setActiveTree=staticmethod(_setActiveTree)

    def restoreContext(self):
        """Internal use only. Use internal context associated with this tree."""
        Tree._setActiveTree(self)
        _TreeShr.TreeSwitchDbid(self.ctx)

    def setActiveTree(cls,tree):
        """Set active tree. Use supplied tree context when performing tree operations in tdi expressions.
        @param tree: Tree to use as active tree
        @type tree: Tree
        @return: Previous active tree
        @rtype: Tree
        """
        old = cls._setActiveTree(tree)
        if tree is not None:
          tree.restoreContext()
        return old
    setActiveTree=classmethod(setActiveTree)

    def setCurrent(treename,shot):
        """Set current shot for specified treename
        @param treename: Name of tree
        @type treename: str
        @param shot: Shot number
        @type shot: int
        @rtype None
        """
        try:
            Tree.lock()
            status=_TreeShr.TreeSetCurrentShotId(_C.c_char_p(str.encode(str(treename))),_C.c_int32(int(shot)))
        finally:
            Tree.unlock()
        if not (status & 1):
            raise TreeException('Error setting current shot of %s: %s' % (treename,MdsGetMsg(status)))
    setCurrent=staticmethod(setCurrent)

    def setDefault(self,node):
        """Set current default TreeNode.
        @param node: Node to make current default. Relative node paths will use the current default when resolving node lookups.
        @type node: TreeNode
        @return: Previous default node
        @rtype: TreeNode
        """
        old=self.default
        if isinstance(node,TreeNode):
            if node.tree is self:
                status = _TreeShr._TreeSetDefaultNid(self.ctx,_C.c_int32(node.nid))
                if (status & 1) == 0:
                  raise TreeException('Error setting default: %s' % (_data.getStatusMsg(status),))
            else:
                raise TypeError('TreeNode must be in same tree')
        else:
            raise TypeError('default node must be a TreeNode')
        return old
    
    def setTimeContext(begin,end,delta):
        """Set time context for retrieving segmented records
        @param begin: Time value for beginning of segment.
        @type begin: Data
        @param end: Ending time value for segment of data
        @type end: Data
        @param delta: Delta time for sampling segment
        @type delta: Data
        @rtype: None
        """
        TreeSetTimeContext(begin,end,delta)
    setTimeContext=staticmethod(setTimeContext)

    def setVersionDate(date):
        """Set date for retrieving versions if versioning is enabled in tree.
        @param date: Reference date for data retrieval. Must be specified in the format: 'mmm-dd-yyyy hh:mm:ss' or 'now','today'
        or 'yesterday'.
        @type date: str
        @rtype: None
        """
        TreeSetVersionDate(date)
    setVersionDate=staticmethod(setVersionDate)

    def setVersionsInModel(self,flag):
        """Enable/Disable versions in model
        @param flag: True or False. True enables versions
        @type flag: bool
        @rtype: None
        """
        self.versions_in_model=bool(flag)

    def setVersionsInPulse(self,flag):
        """Enable/Disable versions in pulse
        @param flag: True or False. True enabled versions
        @type flag: bool
        @rtype: None
        """
        self.versions_in_pulse=bool(flag)

    def unlock(cls):
        """Internal use only. Thread synchronization locking.
        """
        if not _TreeShr.TreeUsingPrivateCtx():
            cls._lock.release()
    unlock=classmethod(unlock)

    def versionsInModelEnabled(self):
        """Check to see if versions in the model are enabled
        @return: True if versions in model is enabled
        @rtype: bool
        """
        return self.versions_in_model
    
    def versionsInPulseEnabled(self):
        """Check to see if versions in the pulse are enabled
        @return: True if versions in pulse is enabled
        @rtype: bool
        """
        return self.versions_in_pulse

    def write(self):
        """Write out edited tree.
        @rtype: None
        """
        try:
            name=self.tree
            shot=self.shot
            Tree.lock()
            status = _TreeShr._TreeWriteTree(_C.pointer(self.ctx),_C.c_char_p(str.encode(name)),_C.c_int32(shot))
            if (status & 1) == 0:
              raise TreeException('Error writing tree, error: %s' % (_data.getStatusMsg(status),))
        finally:
            Tree.unlock()

class TreeNode(_data.Data):
    """Class to represent an MDSplus node reference (nid).
    @ivar nid: node index of this node.
    @type nid: int
    @ivar tree: Tree instance that this node belongs to.
    @type tree: Tree
    """
    mdsclass=1
    dtype_mds=192
    mdsdtypeToClass=dict()

    def __hasBadTreeReferences__(self,tree):
      return self.tree != tree

    def __fixTreeReferences__(self,tree):
        if (self.nid >> 24) != 0:
            return TreePath(str(self))
        else:
            relpath=str(self.fullpath)
            relpath=relpath[relpath.find('::TOP')+5:]
            path='\\%s::TOP%s' % (tree.tree,relpath)
            try:
                ans=tree.getNode(str(self))
            except:
                ans=TreePath(path,tree)
            return ans
    
    def _getDescriptor(self):
      """Return a MDSplus descriptor"""
      d=_data._Descriptor()
      d.length=4
      d.dtype=self.dtype_mds
      d.dclass=self.mdsclass
      d.pointer=_C.cast(_C.pointer(_C.c_int32(self.nid)),_C.c_void_p)
      d.original=self
      d.tree=self.tree
      return _data._descrWithUnitsAndError(self,d)
    descriptor=property(_getDescriptor,)

    def __getattr__(self,name_in):
        """
        Implements value=node.attribute
        
        Attributes defined:

         - brother               - TreeNode,Next node in tree
         - child                 - TreeNode,First ancestor
         - children_nids         - TreeNodeArray, Children nodes
         - mclass                - Uint8, Internal numeric MDSplus descriptor class
         - class_str             - String, Name of MDSplus descriptor class
         - compressible          - Bool, Flag indicating node contains compressible data
         - compress_on_put       - Bool, Flag indicating automatic compression
         - conglomerate_elt      - Int32, Index of node in a conglomerate
         - conglomerate_nids     - TreeNodeArray, Nodes in same conglomerate
         - data_in_nci           - Uint32, Flag indicating data stored in nci record
         - descendants           - TreeNodeArray, One level descendants of this node
         - depth                 - Int32, Level of node from the top node of the tree
         - disabled              - Bool, Opposite of on flag
         - do_not_compress       - Bool, Flag indicating data should not be compressed
         - dtype                 - Uint8, Internal numeric MDSplus data type
         - dtype_str             - String, Name of MDSplus data type
         - essential             - Bool, Flag indicating node is essential, used for actions
         - fullpath              - String, Full absolute path of node in tree
         - include_in_pulse      - Bool, Flag indicating node should be included in pulse
         - is_child              - Bool, Flag indicating node is a child node
         - is_member             - Bool, Flag indicating node is a member bnode
         - length                - Int32, Length of data in bytes (uncompressed)
         - local_path            - str, path to node relative to top of tree containing this node
         - local_tree            - str, Name of tree containing this node
         - member                - TreeNode, First member of this node
         - member_nids           - TreeNodeArray, Members nodes
         - minpath               - String, Minimum length string representing path to node
         - nid_number            - Int32, Internal index to node in tree
         - nid_reference         - Bool, Flag indicating that data contains references to nodes
         - node_name             - String, This nodes name
         - no_write_model        - Bool, Flag indicating that data cannot be written into model
         - no_write_shot         - Bool, Flag indicating that data cannot be written into shot
         - number_of_children    - Int32, Number of children of this node
         - number_of_descentants - Int32, Numer of first level descendants
         - number_of elts        - Int32, Number of nodes in this conglomerate
         - number_of_members     - Int32, Number of members of this node
         - on                    - Bool, Flag indicating if this node is turned on
         - original_part_name    - String, Original node name when conglomerate was created
         - owner_id              - Int32, Id/gid of account which stored the data
         - parent                - TreeNode, Parent of this node
         - parent_disabled       - Bool, Flag indicating parent is turned off
         - path                  - String, Path to this node
         - path_reference        - Bool, Flag indicating that data contains references to nodes
         - record                - Data, Contents of this node
         - rfa                   - Int64, Byte offset to this node
         - rlength               - Int32, Data length in bytes (compressed)
         - segmented             - Bool, Flag indicating node contains segmented records
         - setup_information     - Bool, Flag indicating node contains setup information
         - status                - Int32, Completion status of action
         - tags                  - StringArray, List of tagnames for this node
         - time_inserted         - Uint64, Time data was inserted
         - usage                 - String, Usage of this node
         - versions              - Bool, Flag indicating that data contains versions
         - write_once            - Bool, Flag indicating that data can only be written if node is empty.
         @param name: Name of attribute
         @type name: str
         @return: Value of attribute
         @rtype: various
         """
        if name_in.lower() == 'nid':
          return self.tree.getNode(self.tree_path).nid
        return self.getNci(name_in,False)

    def __init__(self,n,tree=None):
        """Initialze TreeNode
        @param n: Index of the node in the tree.
        @type n: int
        @param tree: Tree associated with this node
        @type tree: Tree
        """
        self.__dict__['nid']=int(n);
        if tree is None:
            try:
                self.tree=Tree.getActiveTree()
            except:
                self.tree=Tree()
        else:
            self.tree=tree
    
    def __setattr__(self,name_in,value):
        """
        Implements node.attribute=value

        Attributes which can be set:

         - compress_on_put  - Bool, Flag indicating whether data should be compressed when written
         - do_not_compress  - Bool, Flag to disable compression
         - essential        - Bool, Flag indicating successful action completion required
         - include_in_pulse - Bool, Flag to include in pulse
         - no_write_model   - Bool, Flag to disable writing in model
         - no_write_shot    - Bool, Flag to disable writing in pulse file
         - record           - Data, Data contents of node
         - subtree          - Bool, Set node to be subtree or not (edit mode only)
         - tag              - str, Add tag to node (edit mode only)
         - write_once       - Bool, Flag to only allow writing to empty node
        @param name: Name of attribute
        @type name: str
        @param value: Value for attribute
        @type value: various
        @rtype: None
        """
        uname=name_in.upper()
        if uname=="RECORD":
            self.putData(value)
        elif uname=="ON":
            self.setOn(value)
        elif uname=="NO_WRITE_MODEL":
            self.setNoWriteModel(value)
        elif uname=="NO_WRITE_SHOT":
            self.setNoWriteShot(value)
        elif uname=="WRITE_ONCE":
            self.setWriteOnce(value)
        elif uname=="INCLUDE_IN_PULSE":
            self.setIncludedInPulse(value)
        elif uname=="COMPRESS_ON_PUT":
            self.setCompressOnPut(value)
        elif uname=="DO_NOT_COMPRESS":
            self.setDoNotCompress(value)
        elif uname=="ESSENTIAL":
            self.setEssential(value)
        elif uname=="SUBTREE":
            self.setSubtree(value)
        elif uname=="USAGE":
            self.setUsage(value)
        elif uname=="TAG":
            self.addTag(value)
        elif uname == "NID":
            raise AttributeError('Attribute nid is read only')
        else:
            self.__dict__[name_in]=value

    def __str__(self):
      """Convert TreeNode to string."""
      if self.nid is None:
        ans="NODEREF(*)"
      else:
        return str(self.path)

    def addDevice(self,name,model):
        """Add device descendant.
        @param name: Node name of device. 1-12 characters, no path delimiters
        @type name: str
        @param model: Type of device to add
        @type model: str
        @return: Head node of device
        @rtype: TreeNode
        """
        if name.find(':') >=0 or name.find('.') >= 0:
            raise TreeException("Invalid node name, do not include path delimiters in nodename")
        return self.tree.addDevice(self.fullpath+":"+name.upper(),model)

    def addNode(self,name,usage='ANY'):
        """Add node
        @param name: Node name of new node to add
        @type name: str
        @param usage: Usage of the new node. If omitted set to ANY.
        @type usage: str
        @return: New now added
        @rtype: TreeNode
        """
        try:
            usagenum=_usageTable[usage.upper()]
        except KeyError:
            raise KeyError('Invalid usage specified. Use one of %s' % (str(_usageTable.keys()),))
        name=str(name).upper()
        if name[0]==':' or name[0]=='.':
            name=str(self.fullpath)+name
        elif name[0] != "\\":
            if usagenum==1 or usagenum==-1:
                name=str(self.fullpath)+"."+name
            else:
                name=str(self.fullpath)+":"+name
        return self.tree.addNode(name,usage)

    def addTag(self,tag):
        """Add a tagname to this node
        @param tag: tagname for this node
        @type tag: str
        @rtype: None
        """
        _TreeShr._TreeAddTag(self.tree.ctx,self.nid,_C.c_char_p(str.encode(tag)))

    def beginSegment(self,start,end,dimension,initialValueArray,idx=-1):
        """Begin a record segment
        @param start: Index of first row of data
        @type start: Data
        @param end: Index of last row of data
        @type end: Data
        @param dimension: Dimension information of segment
        @type dimension: Dimension
        @param initialValueArray: Initial data array. Defines shape of segment
        @type initialValueArray: Array
        @rtype: None
        """
        try:
          Tree.lock()
          status=_TreeShr._TreeBeginSegment(self.tree.ctx,_C.c_int32(self.nid),
                                            _C.pointer(_data.makeData(start).descriptor),
                                            _C.pointer(_data.makeData(end).descriptor),
                                            _C.pointer(_data.makeData(dimension).descriptor),
                                            _C.pointer(_data.makeData(initialValueArray).descriptor),
                                            _C.c_int32(idx))
        finally:
          Tree.unlock()
        if (status & 1) == 0:
          raise TreeException("Error beginning segment: %s" % _data.getStatusMsg(status))

    def beginTimestampedSegment(self,array,idx=-1):
        """Allocate space for a timestamped segment
        @param array: Initial data array to define shape of segment
        @type array: Array
        @param idx: Optional segment index. Defaults to -1 meaning next segment.
        @type idx: int
        @rtype: None
        """
        try:
          Tree.lock()
          status=_TreeShr._TreeBeginTimestampedSegment(self.tree.ctx,_C.c_int32(self.nid),
                                                       _C.pointer(_data.makeData(value).descriptor),
                                                       _C.c_int32(idx))
        finally:
          Tree.unlock()
        if (status & 1)==0:
          raise TreeException("Error beginning timestamped segment: %s" % _data.getStatusMsg(status))

    def compare(self,value):
        """Returns True if this node contains the same data as specified in the value argument
        @param value: Value to compare contents of the node with
        @type value: Data
        @rtype: Bool
        """
        if isinstance(value,TreePath) and isinstance(self,TreePath):
          ans=str(self)==str(value)
        elif type(self)==TreeNode and type(value)==TreeNode:
          ans=self.nid==value.nid and self.tree==value.tree
        else:
          try:
            ans=value.compare(self.record)
          except:
            ans=value is None
        return ans

    def containsVersions(self):
        """Return true if this node contains data versions
        @return: True if node contains versions
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x10) != 0

    def delete(self):
        """Delete this node from the tree
        @rtype: None
        """
        self.tree.deleteNode(self.fullpath)

    def deleteData(self):
        """Delete data from this node
        @rtype: None
        """
        self.putData(None)
        return

    def dispatch(self,wait=True):
        """Dispatch an action node
        @rtype: None
        """
        a=self.record
        if not isinstance(a,_compound.Action):
            raise Exception("Node does not contain an action description")
        else:
            if wait:
                status=Data.TCL("dispatch/wait "+str(self.fullpath))
            else:
                status=Data.TCL("dispatch/nowait "+str(self.fullpath))
            if not (status & 1):
                raise Exception(_mdsshr.MdsGetMsg(status,"Error dispatching node"))

    def doMethod(self,method,arg=None):
        """Execute method on conglomerate element
        @param method: method name to perform
        @type method: str
        @param arg: Optional argument for method
        @type arg: Data
        @rtype: None
        """
        try:
            Tree.lock()
            self.restoreContext()
            TreeDoMethod(self,str(method),arg)
        finally:
            Tree.unlock()
        return

    def getBrother(self):
        """Return sibling of this node
        @return: Sibling of this node
        @rtype: TreeNode
        """
        return self.getNci('brother',False)

    def getChild(self):
        """Return first child of this node.
        @return: Return first child of this node or None if it has no children.
        @rtype: TreeNode
        """
        return self.getNci('child',False)

    def getChildren(self):
        """Return TreeNodeArray of children nodes.
        @return: Children of this node
        @rtype: TreeNodeArray
        """
        child=self.getNci('child',False)
        if child is not None:
          nids=[child.nid,]
          brother=child.getNci('brother')
          while brother is not None:
            nids.append(brother.nid)
            brother=brother.getNci('brother')
          return TreeNodeArray(nids,self.tree)
        else:
          return None

    def getClass(self):
        """Return MDSplus class name of this node
        @return: MDSplus class name of the data stored in this node.
        @rtype: String
        """
        return self.getNci('class_str',False)

    def getCompressedLength(self):
        """Return compressed data length of this node
        @return: Compress data length of this node
        @rtype: int
        """
        return self.getNci('rlength',False)

    def getConglomerateElt(self):
        """Return index of this node in a conglomerate
        @return: element index of this node in a conglomerate. 0 if not in a conglomerate.
        @rtype: Int32
        """
        return self.getNci('conglomerate_elt',False)
    
    def getConglomerateNodes(self):
        """Return TreeNodeArray of conglomerate elements
        @return: Nodes in this conglomerate.
        @rtype: TreeNodeArray,None
        """
        nci=self.getNci(['conglomerate_elt','number_of_elts'])
        if nci['number_of_elts'] > 0:
          first=self.nid-int(nci['conglomerate_elt'])+1
          last=self.nid-int(nci['conglomerate_elt'])+int(nci['number_of_elts'])+1
          return TreeNodeArray(list(range(first,last)),self.tree)
        else:
          return None

    def getData(self,raiseNoData=True):
        """Return data
        @return: data stored in this node
        @rtype: Data
        """
        value=_data._Descriptor_xd()
        status = _TreeShr._TreeGetRecord(self.tree.ctx,_C.c_int32(self.nid),_C.pointer(value))
        if status == 265388258:
          if raiseNoData:
            raise TreeNoDataException("No data stored in node %s" % (str(self),))
          else:
            return None
        if (status & 1)==0:
          raise TreeException("Error retrieving data for node %s" % (str(Self),))
        else:
          _data._Descriptor.tree=self.tree
          ans=value.value
          _data._Descriptor.tree=None
          return ans

    def getDataNoRaise(self):
        """Return data
        @return: data stored in this node
        @rtype: Data
        """
        return self.getData(raiseNoData=False)

    def getDepth(self):
        """Get depth of this node in the tree
        @return: number of levels between this node and the top of the currently opened tree.
        @rtype: Int32
        """
        return self.getNci('depth',False)

    def getDescendants(self):
        """Return TreeNodeArray of first level descendants (children and members).
        @return: First level descendants of this node
        @rtype: TreeNodeArray,None
        """
        ans=None
        members=self.getMembers()
        children=self.getChildren()
        if members is None:
          ans=children
        elif children is None:
          ans=members
        else:
          nids=list()
          for node in members:
            nids.append(node.nid)
          for node in children:
            nids.append(node.nid)
          ans=TreeNodeArray(nids)
        return ans
            
    def getDtype(self):
        """Return the name of the data type stored in this node
        @return: MDSplus data type name of data stored in this node.
        @rtype: String
        """
        return self.getNci('dtype_str',False)
    
    def getFullPath(self):
        """Return full path of this node
        @return: full path specification of this node.
        @rtype: String
        """
        return self.getNci('fullpath',False)

    def getLength(self):
        """Return uncompressed data length of this node
        @return: Uncompressed data length of this node
        @rtype: int
        """
        return int(self.getNci('length',False))

    def getNci(self,items_in=None,returnDict=True):
        """Return dictionary of nci items"""
        class NCI_ITEMS(_C.Structure):
          _fields_=list()
          for idx in range(50):
            _fields_+=[("buffer_length%d"%idx,_C.c_ushort)]+[("code%d"%idx,_C.c_ushort)]+[("pointer%d"%idx,_C.c_void_p)]+[("retlen%d"%idx,_C.POINTER(_C.c_int32))]
    
          def __init__(self,fields):
            for idx in range(len(fields)):
              fields[idx]['retlen']=_C.c_int32(0)
              self.__setattr__('code%d'%idx,_C.c_ushort(fields[idx]['code']))
              if isinstance(fields[idx]['pointer'],_C.c_char_p):
                fields[idx]['buflen']=len(fields[idx]['pointer'].value)
                self.__setattr__('pointer%d'%idx,_C.cast(fields[idx]['pointer'],_C.c_void_p))
              else:
                fields[idx]['buflen']=_C.sizeof(fields[idx]['pointer'])
                self.__setattr__('pointer%d'%idx,_C.cast(_C.pointer(fields[idx]['pointer']),_C.c_void_p))
              self.__setattr__('buffer_length%d'%idx,_C.c_ushort(fields[idx]['buflen']))
              self.__setattr__('retlen%d'%idx,_C.pointer(fields[idx]['retlen']))

        fielddefs={'end':                {'code':0,  'pointer':_C.c_void_p(0)},
    #              'set_flags':          {'code':1,  'pointer':_C.c_int32(0)},
    #              'clear_flags':        {'code':2,  'pointer':_C.c_int32(0)},
                   'time_inserted':      {'code':4,  'pointer':_C.c_uint64(0)},
                   'owner_id':           {'code':5,  'pointer':_C.c_int32(0)},
                   'mclass':             {'code':6,  'pointer':_C.c_uint8(0)},
                   'dtype':              {'code':7,  'pointer':_C.c_uint8(0)},
                   'length':             {'code':8,  'pointer':_C.c_int32(0)},
                   'status':             {'code':9,  'pointer':_C.c_int32(0)},
                   'conglomerate_elt':   {'code':10, 'pointer':_C.c_int32(0)},
                   'flags':              {'code':12, 'pointer':_C.c_int32(0)},
                   'node_name':          {'code':13, 'pointer':_C.c_char_p(str.encode(' ')*1024)},
                   'path':               {'code':14, 'pointer':_C.c_char_p(str.encode(' ')*1024)},
                   'depth':              {'code':15, 'pointer':_C.c_int32(0)},
                   'parent':             {'code':16, 'pointer':_C.c_int32(0)},
                   'brother':            {'code':17, 'pointer':_C.c_int32(0)},
                   'member':             {'code':18, 'pointer':_C.c_int32(0)},
                   'child':              {'code':19, 'pointer':_C.c_int32(0)},
                   'parent_relationship':{'code':20, 'pointer':_C.c_int32(0)},
    #              'conglomerate_nids':  {'code':21, 'pointer':.....
                   'original_part_name': {'code':22, 'pointer':_C.c_char_p(str.encode(' ')*1024)},
                   'number_of_members':  {'code':23, 'pointer':_C.c_int32(0)},
                   'number_of_children': {'code':24, 'pointer':_C.c_int32(0)},
    #              'member_nids':        {'code':25, 'pointer':....
    #              'children_nids':      {'code':26, 'pointer':...
                   'fullpath':           {'code':27, 'pointer':_C.c_char_p(str.encode(' ')*1024)},
                   'minpath':            {'code':28, 'pointer':_C.c_char_p(str.encode(' ')*1024)},
                   'usage_num':          {'code':29, 'pointer':_C.c_byte(0)},
                   'parent_tree':        {'code':30, 'pointer':_C.c_char_p(str.encode(' ')*1024)},
                   'rlength':            {'code':31, 'pointer':_C.c_int32(0)},
                   'number_of_elts':     {'code':32, 'pointer':_C.c_int32(0)},
                   'data_in_nci':        {'code':33, 'pointer':_C.c_bool(False)},
                   'error_on_put':       {'code':34, 'pointer':_C.c_bool(False)},
                   'rfa':                {'code':35, 'pointer':_C.c_uint64(0)},
                   'io_status':          {'code':36, 'pointer':_C.c_int32(0)},
                   'io_stv':             {'code':37, 'pointer':_C.c_int32(0)},
                   'dtype_str':          {'code':38, 'pointer':_C.c_char_p(str.encode(' ')*64)},
                   'usage_str':          {'code':39, 'pointer':_C.c_char_p(str.encode(' ')*64)},
                   'class_str':          {'code':40, 'pointer':_C.c_char_p(str.encode(' ')*64)},
                   'version':            {'code':41, 'pointer':_C.c_int32(0)},
                   }
 
        specialdefs={'conglomerate_nids':self.getConglomerateNodes,'member_nids':self.getMembers,'children_nids':self.getChildren,
                     'cached':self.isCached,'compressible':self.isCompressible,'compress_on_put':self.isCompressOnPut,
                     'disabled':self.isDisabled,'do_not_compress':self.isDoNotCompress,'essential':self.isEssential,
                     'include_in_pulse':self.isIncludedInPulse,'is_child':self.isChild,
                     'is_member':self.isMember,'nid_number':self.getNid,'nid_reference':self.hasNodeReferences,
                     'no_write_model':self.isNoWriteModel,'no_write_shot':self.isNoWriteShot,'on':self.isOn,
                     'parent_disabled':self.isParentDisabled,'parent_state':self.isParentDisabled,'path_reference':self.hasPathReferences,
                     'segmented':self.isSegmented,'setup_information':self.isSetup,'state':self.isDisabled,'versions':self.containsVersions,
                     'write_once':self.isWriteOnce,'number_of_descendants':self.getNumDescendants,'descendants':self.getDescendants,
                     'local_tree':self.getLocalTree,'local_path':self.getLocalPath,'tags':self.getTags,'usage':self.getUsage,
                     'record':self.getDataNoRaise,'descriptor':self._getDescriptor}
        fieldTranslations={'get_flags':'flags',}
        nodedefs=('member','child','parent','brother')
        quad=type(_C.c_int64(0).value)
        itemlist={'SET_FLAGS':(1,int),'CLEAR_FLAGS':(2,int),'TIME_INSERTED':(4,quad),
                  'OWNER_ID':(5,quad),'CLASS':(6,bool),'DTYPE':(7,bool),
                  'LENGTH':(8,int),'STATUS':(9,int),'CONFLOMERATE_ELT':(10,bool),
                  'GET_FLAGS':(12,int),'NODE_NAME':(13,str,12),
                  'PATH':(14,str,512),'DEPTH':(15,int),'PARENT':(16,int),'BROTHER':(17,int),
                  'MEMBER':(18,int),'CHILD':(19,int),'PARENT_RELATIONSHIP':(20,bool),
                  'CONGLOMERATE_NIDS':(21,float),'ORIGNAL_PART_NAME':(22,str,512),
                  'NUMBER_OF_MEMBERS':(23,int),'NUMBER_OF_CHILDREN':(24,int),
                  'MEMBER_NIDS':(25,float),'CHILDREN_NIDS':(26,float),'FULLPATH':(27,str,512),
                  'MINPATH':(28,str,512),'USAGE':(29,bool),'PARENT_TREE':(30,str,12),'RLENGTH':(31,int),
                  'NUMBER_OF_ELTS':(32,int),'DATA_IN_NCI':(33,bool),'ERROR_ON_PUT':(34,bool),
                  'RFA':(35,str,12),'IO_STATUS':(36,int),'IO_STV':(37,int),'DTYPE_STR':(38,str,32),
                  'USAGE_STR':(39,str,32),'CLASS_STR':(40,str,32),'VERSION':(41,int),}
        if self.tree is None:
          self.tree=Tree.getActiveTree()
          if self.tree is None:
            raise TreeException('No tree currently open')
        if items_in is None:
          items=fielddefs.keys()+list(specialdefs)
          items.remove('end')
        elif isinstance(items_in,str):
          items=[items_in,]
        else:
          items=items_in
        items=list(items)
        items.sort()
        fields=list()
        for item in items:
          if item.lower() in fieldTranslations:
            item=fieldTranslations[item.lower()]
          if item.lower() in fielddefs:
            fields.append(fielddefs[item.lower()])
          elif item.lower() in specialdefs:
            pass
          else:
            raise AttributeError("type object '%s' has no attribute '%s'" % (type(self).__name__,item))
        fields.append(fielddefs['end'])
        itmlst=NCI_ITEMS(fields)
        try:
          Tree.lock()
          if len(fields) > 1:
            status=_TreeShr._TreeGetNci(self.tree.ctx,_C.c_int32(self.nid),_C.pointer(itmlst))
          else:
            status=1
          if (status & 1)==1:
            ans=dict()
            for item in items:
              item=item.lower()
              if item in fielddefs:
                fdef=fielddefs[item]
                if fdef['retlen'].value > 0:
                  if isinstance(fdef['pointer'],_C.c_char_p):
                    strans=fdef['pointer'].value[0:fdef['retlen'].value]
                    if not isinstance(strans,str):
                      strans=strans.decode()
                    ans[item]=_data.makeData(strans)
                  else:
                    ans[item]=_data.makeData(fdef['pointer'])
                    if item in nodedefs:
                      ans[item]=TreeNode(int(ans[item]),self.tree)
                else:
                  ans[item]=None
              else:
                ans[item]=specialdefs[item]()
            if len(ans) == 1 and not returnDict:
              ans = ans[items[0]]
        except Exception:
          print(_sys.exc_info()[1])
          Tree.unlock()
        if (status & 1)==0:
          raise TreeException(_data.getStatusMsg(status))
        return ans

    def getLocalTree(self):
        """Return tree containing this node
        @return: Name of tree containing this node
        @rtype: str
        """
        top=self
        while (top.nid & 0xffffff)!=0:
            top=top.parent
        if top.node_name == 'TOP':
            return self.tree.tree
        else:
            return top.node_name

    def getLocalPath(self):
        """Return path relative to top of local tree
        @return: Path relative to top of local tree
        @rtype: str
        """
        path=''
        top=self
        while top.nid & 0xffffff:
            if top.is_member:
                delim=':'
            else:
                delim='.'
            path=delim + top.node_name + path
            top=top.parent
        return path

    def getMember(self):
        """Return first member node
        @return: First member of thie node
        @rtype: TreeNode
        """
        return self.getNci('member',False)

    def getMembers(self):
        """Return TreeNodeArray of this nodes members
        @return: members of this node
        @rtype: TreeNodeArray
        """
        member=self.getNci('member',False)
        if member is not None:
          nids=[member.nid,]
          brother=member.getNci('brother',False)
          while brother is not None:
            nids.append(brother.nid)
            brother=brother.getNci('brother',False)
          return TreeNodeArray(nids,self.tree)
        else:
          return None

    def getMinPath(self):
        """Return shortest path string for this node
        @return: shortest path designation depending on the current node default and whether the node has tag names or not.
        @rtype: String
        """
        return self.getNci('minpath',False)
    
    def getNid(self):
        """Return node index
        @return: Internal node index of this node
        @rtype: int
        """
        return self.nid

    def getNode(self,path):
        """Return tree node where path is relative to this node
        @param path: Path relative to this node
        @type path: str
        @return: node matching path
        @rtype: TreeNode
        """
        if path[0] == '\\':
            return self.tree.getNode(path)
        else:
            if path[0] != ':' and path[0] != '.':
                path=':'+path
            return self.tree.getNode(self.fullpath+path)

    def getNodeName(self):
        """Return node name
        @return: Node name of this node. 1 to 12 characters
        @rtype: String
        """
        return self.getNci('node_name',False)
    
    def getNodeWild(self,path):
        """Return tree nodes where path is relative to this node
        @param path: Path relative to this node
        @type path: str
        @return: node matching path
        @rtype: TreeNodeArray
        """
        if path[0] == '\\':
            return self.tree.getNode(path)
        else:
            if path[0] != ':' and path[0] != '.':
                path=':'+path
            return self.tree.getNodeWild(self.fullpath+path)

    def getNumChildren(self):
        """Return number of children nodes.
        @return: Number of children
        @rtype: Int32
        """
        return self.getNci('number_of_children',False)

    def getNumDescendants(self):
        """Return number of first level descendants (children and members)
        @return: total number of first level descendants of this node
        @rtype: int
        """
        return self.getNumChildren()+self.getNumMembers()

    def getNumElts(self):
        """Return number of nodes in this conglomerate
        @return: Number of nodes in this conglomerate or 0 if not in a conglomerate.
        @rtype: Int32
        """
        return self.getNci('number_of_elts',False)

    def getNumMembers(self):
        """Return number of members
        @return: number of members
        @rtype: int
        """
        return self.getNci('number_of_members',False)

    def getNumSegments(self):
        """return number of segments contained in this node
        @rtype: int
        """
        num=_C.c_int32(0)
        status = _TreeShr._TreeGetNumSegments(self.tree.ctx,_C.c_int32(self.nid),_C.pointer(num))
        if (status & 1) == 0:
          raise TreeException('Cannot determine number of segments, error: %s' % _data.getStatusMsg(status))
        return _data.Int32(num.value)

    def getOriginalPartName(self):
        """Return the original part name of node in conglomerate
        @return: Original part name of this node when conglomerate was first instantiated.
        @rtype: String
        """
        return self.getNci('original_part_name',False)

    def getOwnerId(self):
        """Get id/gid value of account which wrote data to this node
        @return: Return user id of last account used to write data to this node
        @rtype: int
        """
        return self.getNci('owner_id',False)
    
    def getParent(self):
        """Return parent of this node
        @return: Parent of this node
        @rtype: TreeNode
        """
        if nid==0:
          return None
        else:
          return self.getNci('parent',False)

    def getPath(self):
        """Return path of this node
        @return: Path to this node.
        @rtype: String
        """
        return self.getNci('path',False)

    def getSegment(self,idx):
        """Return segment
        @param idx: The index of the segment to return. Indexes start with 0.
        @type idx: int
        @return: Data segment
        @rtype: Signal | None
        """
        num=self.getNumSegments()
        if num > 0 and idx < num:
          data_xd=_data._Descriptor_xd()
          dim_xd=_data._Descriptor_xd()
          status = _TreeShr._TreeGetSegment(self.tree.ctx,_C.c_int32(self.nid),_C.c_int32(idx),_C.pointer(data_xd),_C.pointer(dim_xd))
          if (status & 1) == 1:
            ans = _data.Signal(data_xd.value,None,dim_xd.value)
          else:
            raise TreeException('Error getting segment: %s' % _data.getStatusMsg(status))
        else:
            ans = None
        return ans

    def getSegmentDim(self,idx):
        """Return dimension of segment
        @param idx: The index of the segment to return. Indexes start with 0.
        @type idx: int
        @return: Segment dimension
        @rtype: Dimension
        """
        num=self.getNumSegments()
        if num > 0 and idx < num:
            return self.getSegment(idx).getDimension(0)
        else:
            return None

    def getSegmentEnd(self,idx):
        """return end of segment
        @param idx: segment index to query
        @type idx: int
        @rtype: Data
        """
        num=self.getNumSegments()
        if num > 0 and idx < num:
          startlim=_data._Descriptor_xd()
          endlim=_data._Descriptor_xd()
          status = _TreeShr._TreeGetSegmentLimits(self.tree.ctx,_C.c_int32(self.nid),_C.c_int32(idx),
                                                  _C.pointer(startlim),_C.pointer(endlim))
          if (status & 1)==1:
            try:
              ans=endlim.value.evaluate()
            except:
              ans=None
          else:
            raise TreeException('Error getting segment limits: %s' % _data.getStatusMsg(status))
        else:
          ans = None
        return ans

    def getSegmentStart(self,idx):
        """return start of segment
        @param idx: segment index to query
        @type idx: int
        @rtype: Data
        """
        num=self.getNumSegments()
        if num > 0 and idx < num:
          startlim=_data._Descriptor_xd()
          endlim=_data._Descriptor_xd()
          status = _TreeShr._TreeGetSegmentLimits(self.tree.ctx,_C.c_int32(self.nid),_C.c_int32(idx),
                                                  _C.pointer(startlim),_C.pointer(endlim))
          if (status & 1)==1:
            try:
              ans=startlim.value.evaluate()
            except:
              ans=None
          else:
            raise TreeException('Error getting segment limits: %s' % _data.getStatusMsg(status))
        else:
          ans = None
        return ans

    def getStatus(self):
        """Return action completion status
        @return: action completion status stored by dispatcher if this node is a dispacted action. Low bit set is success.
        @rtype: int
        """
        return self.getNci('status',False)
    
    def getTimeInserted(self):
        """Return time data was written
        @return: time data was written to this node as Uint64. Use answer.date to retrieve date/time string
        @rtype: Uint64
        """
        return self.getNci('time_inserted',False)

    def getTags(self):
      """Return tags of this node
      @return: Tag names pointing to this node
      @rtype: StringArray
      """
      ans=None
      try:
        Tree.lock()
        fnt=_TreeShr._TreeFindNodeTags
        fnt.restype=_C.c_void_p
        ctx=_C.c_void_p(0)
        tags=list()
        done=False
        tag_ptr=fnt(self.tree.ctx,_C.c_int32(self.nid),_C.pointer(ctx))
        while tag_ptr:
          tags.append(_C.cast(tag_ptr,_C.c_char_p).value.rstrip())
          _TreeShr.TreeFree(tag_ptr)
          tag_ptr=fnt(self.tree.ctx,_C.c_int32(self.nid),_C.pointer(ctx))
        if len(tags) > 0:
          ans=_data.StringArray(_NP.array(tags))
      finally:
        Tree.unlock()
      return ans

    def getTree(self):
        """Return Tree associated with this node
        @return: Tree associated with this node
        @rtype: Tree
        """
        return self.tree

    def getUsage(self):
        """Return usage of this node
        @return: usage of this node
        @rtype: str
        """
        return self.usage_str[10:]

    def hasNodeReferences(self):
      """Return True if this node contains data that includes references
      to other nodes in the same tree
      @return: True of data references other nodes
      @rtype: bool
      """
      return (self.getNci('flags',False) & 0x4000) !=0

    def hasPathReferences(self):
      """Return True if this node contains node references using paths.
      This usually means the data references nodes from other subtrees.
      @return: True if data contains node path references
      @rtype: bool
      """
      return (self.getNci('flags',False) & 0x2000) != 0

    def isCached(self):
      """Return true if node data is cached"""
      return (self.getNci('flags',False) & 0x008)!=0
    
    def isChild(self):
        """Return true if this is a child node
        @return: True if this is a child node instead of a member node.
        @rtype: bool
        """
        return self.getNci('parent_relationship',False)==1

    def isCompressible(self):
        """Return true if node contains data which can be compressed
        @return: True of this node contains compressible data
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x100)!=0

    def isCompressOnPut(self):
        """Return true if node is set to compress on put
        @return: True if compress on put
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x400)!=0

    def isCompressSegments(self):
        """Return true if segment compression is enabled for this node
        @return: True if this node has segment compression enabled
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x10000)!=0

    def isDisabled(self):
      """Return true if this node is disabled (opposite of isOn)
      @return: True if node is off
      @rtype: bool
      """
      return not self.isOn()

    def isDoNotCompress(self):
        """Return true if compression is disabled for this node
        @return: True if this node has compression disabled
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x200)!=0

    def isEssential(self):
        """Return true if successful action completion is essential
        @return: True if this node is marked essential.
        @rtype: bool
        """
        return (self.getNci('flags',False) &  0x04)!=0

    def isIncludedInPulse(self):
        """Return true if this subtree is to be included in pulse file
        @return: True if subtree is to be included in pulse file creation.
        @rtype: bool
        """
        return (self.getNci('flags',False) &  0x8000)!=0

    def isMember(self):
        """Return true if this is a member node
        @return:  True if this is a member node
        @rtype: bool
        """
        return self.getNci('parent_relationship',False)==2

    def isNoWriteModel(self):
        """Return true if data storage to model is disabled for this node
        @return: Return True if storing data in this node in the model tree is disabled
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x800)!=0

    def isNoWriteShot(self):
        """Return true if data storage to pulse file is disabled for this node
        @return: Return True if storing data in this node in the pulse tree is disabled
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x1000)!=0

    def isOn(self):
        """Return True if node is turned on, False if not.
        @return: Return True if node is turned on
        @rtype: bool
        """
        return (self.getNci('flags',False) & 3)==0

    def isParentDisabled(self):
      """Return True if parent is disabled
      @return: Return True if parent is turned off
      @rtype: bool
      """
      return not self.isParentOn()

    def isParentOn(self):
      """Return True if parent is on
      @return: Return True if parent is turned on
      @rtype: bool
      """
      return (self.getNci('flags',False) & 0x02)==0

    def isSegmented(self):
        """Return true if this node contains segmented records
        @return: True if node contains segmented records
        @rtype: bool
        """
        return self.getNumSegments()!=0
    
    def isSetup(self):
        """Return true if data is setup information.
        @return: True if data is setup information (originally written in the model)
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x0040) != 0

    def isWriteOnce(self):
        """Return true if node is set write once
        @return: Return True if data overwrite in this node is disabled
        @rtype: bool
        """
        return (self.getNci('flags',False) & 0x80) != 0

    def makeSegment(self,start,end,dimension,valueArray,idx=-1):
        """Make a record segment
        @param start: Index of first row of data
        @type start: Data
        @param end: Index of last row of data
        @type end: Data
        @param dimension: Dimension information of segment
        @type dimension: Dimension
        @param valueArray: Contents of segment
        @type valueArray: Array
        @rtype: None
        """
        TreeMakeSegment(self,start,end,dimension,valueArray,idx)

    def move(self,parent,newname=None):
        """Move node to another location in the tree and optionally rename the node
        @param parent: New parent of this node
        @type parent: TreeNode
        @param newname: Optional new node name of this node. 1-12 characters, no path delimiters.
        @type newname: str
        @rtype: None
        """
        if newname is None:
            newname=str(self.node_name)
        if self.usage=='SUBTREE' or self.usage=='STRUCTURE':
            TreeRenameNode(self,str(parent.fullpath)+"."+newname)
        else:
            TreeRenameNode(self,str(parent.fullpath)+":"+newname)
        
    def putData(self,data):
        """Store data
        @param data: Data to store in this node.
        @type data: Data
        @rtype: None
        """
        try:
            if isinstance(data,_data.Data) and data.__hasBadTreeReferences__(self.tree):
                data=data.__fixTreeReferences__(self.tree)
            Tree.lock()
            status = _TreeShr._TreePutRecord(self.tree.ctx,_C.c_int32(self.nid),_C.pointer(_data.makeData(data).descriptor),_C.c_int32(0))
            if (status & 1)==0:
              raise TreeException("Error putting data: %s" % (_data.getStatusMsg(status),))
        finally:
            Tree.unlock()
        return

    def putRow(self,bufsize,array,timestamp):
        """Load a timestamped segment row
        @param bufsize: number of rows in segment
        @type bufsize: int
        @param array: data for this row
        @type array: Array or Scalar
        @param timestamp: Timestamp of this row
        @type timestamp: Uint64
        @rtype: None
        """
        try:
          Tree.lock()
          status=_TreeShr._TreePutRow(self.tree.ctx,_C.c_int32(self.nid),_C.c_int32(bufsize),
                                      _C.pointer(_C.c_int64(int(timestamp))),
                                      _C.pointer(_data.makeArray(array).descriptor))
        finally:
          Tree.unlock()
        if (status & 1)==0:
          raise TreeException("Error putting row: %s" % _data.getStatusMsg(status))
                
    def putSegment(self,data,idx):
        """Load a segment in a node
        @param data: data to load into segment
        @type data: Array or Scalar
        @param idx: index into segment to load data
        @type idx: int
        @rtype: None
        """
        try:
          Tree.lock()
          status=_TreeShr._TreePutSegment(self.tree.ctx,_C.c_int32(self.nid),_C.c_int32(idx),
                                          _C.pointer(_data.makeData(data).descriptor))
        finally:
          Tree.unlock()
        if (status & 1)==0:
          raise TreeException("Error putting segment: %s" % _data.getStatusMsg(status))

    def putTimestampedSegment(self,timestampArray,array):
        """Load a timestamped segment
        @param timestampArray: Array of time stamps
        @type timestampArray: Uint64Array
        @param array: Data to load into segment
        @type array: Array
        @rtype: None
        """
        timestampArray=_data.Int64Array(timestampArray)
        try:
          Tree.lock()
          status=_TreeShr._TreePutTimestampedSegment(self.tree.ctx,_C.c_int32(self.nid),
                                                     timestampArray.descriptor.pointer,
                                                     _C.pointer(_data.makeArray(value).descriptor))
        finally:
          Tree.unlock()
        if (status & 1)==0:
          raise TreeException("Error putting timestamped segment %s" % _data.getStatusMsg(status))

    def makeTimestampedSegment(self,timestampArray,array,idx,rows_filled):
        """Load a timestamped segment
        @param timestampArray: Array of time stamps
        @type timestampArray: Uint64Array
        @param array: Data to load into segment
        @type array: Array
        @param idx: Segment number
        @param idx: int
        @param rows_filled: Number of rows of segment filled with data
        @type rows_filled: int
        @rtype: None
        """
        timestamps=_data.Int64Array(timestampArray)
        try:
          Tree.lock()
          status=_TreeShr._TreeMakeTimestampedSegment(self.tree.ctx,_C.c_int32(self.nid),
                                                      timestampes.descriptor.pointer,
                                                      _C.pointer(_data.makeArray(value).descriptor),
                                                      _C.c_int32(idx),_C.c_int32(rows_filled))
        finally:
          Tree.unlock()
        if (status & 1)==0:
          raise TreeException("Error making timestamped segment: %s" % _data.getStatusMsg(status))

    def removeTag(self,tag):
        """Remove a tagname from this node
        @param tag: Tagname to remove from this node
        @type tag: str
        @rtype: None
        """
        try:
            n=self.tree.getNode('\\'+str(tag))
            if n.nid != self.nid:
                raise TreeException("Node %s does not have a tag called %s. That tag refers to %s" % (str(self),str(tag),str(n)))
        except TreeException:
            e=_sys.exc_info()[1]
            if str(e).find('TreeNNF') > 0:
                raise TreeException("Tag %s is not defined" % (str(tag),))
            else:
                raise
        self.tree.removeTag(tag)
    
    def rename(self,newname):
        """Rename node this node
        @param newname: new name of this node. 1-12 characters, no path delimiters.
        @type newname: str
        @rtype: None
        """
        if newname.find(':') >=0 or newname.find('.') >= 0:
            raise TreeException("Invalid node name, do not include path delimiters in nodename")
        try:
            olddefault=self.tree.default
            self.tree.setDefault(self.parent)
            if self.isChild():
                newname="."+str(newname)
            TreeRenameNode(self,str(newname))
        finally:
            self.tree.setDefault(olddefault)

    def restoreContext(self):
        """Restore tree context. Used by internal functions.
        @rtype: None
        """
        if self.tree is not None:
            self.tree.restoreContext()

    def setCompressOnPut(self,flag):
        """Set compress on put state of this node
        @param flag: State to set the compress on put characteristic
        @type flag: bool
        @rtype: None
        """
        self._setNciFlag(0x400,flag)

    def _setNciFlag(self,mask,setting):
        class NCI_ITEMS(_C.Structure):
          _fields_=[("buflen",_C.c_ushort),("code",_C.c_ushort),("pointer",_C.POINTER(_C.c_uint32)),("retlen",_C.c_void_p),
                    ("buflen_e",_C.c_ushort),("code_e",_C.c_ushort),("pointer_e",_C.c_void_p),("retlen_e",_C.c_void_p)]
        itmlst=NCI_ITEMS()
        code={True:1,False:2}
        mask=_C.c_uint32(mask)
        itmlst.buflen=0
        itmlst.code=code[setting]
        itmlst.pointer=_C.pointer(mask)
        itmlst.retlen=0
        itmlst.buflen_e=0
        itmlst.code_e=0
        itmlst.pointer_e=0
        itmlst.retlen_e=0
        try:
          Tree.lock()
          status = _TreeShr._TreeSetNci(self.tree.ctx,_C.c_int32(self.nid),_C.pointer(itmlst))
        finally:
          Tree.unlock()
        if (status & 1)==0:
          raise TreeEXception("Error setting compress_on_put: %s" % _data.getStatusMsg(status))

    def setDoNotCompress(self,flag):
        """Set do not compress state of this node
        @param flag: True do disable compression, False to enable compression
        @type flag: bool
        @rtype: None
        """
        self._setNciFlag(0x200,flag)

    def setEssential(self,flag):
        """Set essential state of this node
        @param flag: State to set the essential characteristic. This is used on action nodes when phases are dispacted.
        @type flag: bool
        @rtype: None
        """
        self._setNciFlag(0x04,flag)

    def setIncludedInPulse(self,flag):
        """Set include in pulse state of this node
        @param flag: State to set the include in pulse characteristic. If true and this node is the top node of a subtree the subtree will be included in the pulse.
        @type flag: bool
        @rtype: None
        """
        self._setNciFlag(0x8000,flag)

    def setNoWriteModel(self,flag):
        """Set no write model state for this node
        @param flag: State to set the no write in model characteristic. If true then no data can be stored in this node in the model.
        @type flag: bool
        @rtype: None
        """
        self._setNciFlag(0x800,flag)

    def setNoWriteShot(self,flag):
        """Set no write shot state for this node
        @param flag: State to set the no write in shot characteristic. If true then no data can be stored in this node in a shot file.
        @type flag: bool
        @rtype: None
        """
        self._setNciFlag(0x1000,flag)

    def setOn(self,flag):
        """Turn node on or off
        @param flag: State to set the on characteristic. If true then the node is turned on. If false the node is turned off.
        @type flag: bool
        @rtype: None
        """
        rtn={True:_TreeShr._TreeTurnOn,False:_TreeShr._TreeTurnOff}
        try:
          Tree.lock()
          status = rtn(self.tree.ctx,_C.c_int32(self.nid))
        finally:
          Tree.unlock()
        if (status & 1)==0:
          raise TreeException("Error turning node on or off: %s" % _data.getStatusMsg(status))

    def setSubtree(self,flag):
        """Enable/Disable node as a subtree
        @param flag: True to make node a subtree reference. Node must be a child node with no descendants.
        @type flag: bool
        @rtype: None
        """
        rtn={True:_TreeShr._TreeSetSubtree,False:_TreeShr._TreeSetNoSubtree}
        try:
          Tree.lock()
          status = rtn(self.tree.ctx,_C.c_int32(self.nid))
        finally:
          Tree.unlock()
        if (status & 1)==0:
          raise TreeException("Error setting subtree: %s" % _data.getStatusMsg(status))

    def setUsage(self,usage):
        """Set the usage of a node
        @param usage: Usage string.
        @type flag: str
        @rtype: None
        """
        try:
            usagenum=_usageTable[usage.upper()]
        except KeyError:
            raise KeyError('Invalid usage specified. Use one of %s' % (str(_usageTable.keys()),))
        try:
          status = __TreeShr._TreeSetUsage(self.tree.ctx,_C.c_int32(self.nid),_C.c_byte(usagenum))
        except:
          raise TreeException("Feature not present in current MDSplus installation. Upgrade to newer version of MDSplus.")
        if (status & 1)==0:
          raise TreeException("Error setting node usage: %s" % _data.getStatusMsg(status))
    
    def setTree(self,tree):
        """Set Tree associated with this node
        @param tree: Tree instance to associated with this node
        @type tree: Tree
        @rtype: None
        """
        self.tree=tree

    def setWriteOnce(self,flag):
        """Set write once state of node
        @param flag: State to set the write once characteristic. If true then data can only be written if the node is empty.
        @type flag: bool
        @rtype: None
        """
        self._setNciFlag(0x80,flag)
    
    def updateSegment(self,start,end,dim,idx):
        """Update a segment
        @param start: index of first row of segment
        @type start: Data
        @param end: index of last row of segment
        @type end: Data
        @param dim: Dimension of segment
        @type dim: Dimension
        @param idx: Index of segment
        @type idx: int
        @rtype: None
        """
        try:
          Tree.lock()
          status=_TreeShr._TreeUpdateSegment(self.tree.ctx,_C.c_int32(self.nid),
                                             _C.pointer(_data.makeData(start).descriptor),
                                             _C.pointer(_data.makeData(end).descriptor),
                                             _C.pointer(_data.makeData(dimension).descriptor),_C.c_int32(idx))
        finally:
          Tree.unlock()
        if (status & 1) == 0:
          raise TreeException("Error updating segment: %s" % _data.getStatusMsg(status))

    def _dataFromDescriptor(desc):
      if desc.pointer == _C.c_void_p(0):
        ans = None
      elif desc.dtype == 0:
        ans = _data.EmptyData()
      elif desc.dtype in TreeNode.mdsdtypeToClass:
        klass=TreeNode.mdsdtypeToClass[desc.dtype]
        if issubclass(klass,TreePath):
          if desc.length == 0:
            ans = klass('')
          else:
            ans=klass(str(_NP.array(_C.cast(desc.pointer,_C.POINTER((_C.c_byte*desc.length))).contents[:],dtype=_NP.uint8).tostring().decode()),None)
        elif issubclass(klass,TreeNode):
          ans=klass(_C.cast(desc.pointer,_C.POINTER(_C.c_int32)).contents.value,None)
      else:
        raise Exception("Unsupported dtype: %d" % desc.dtype)
      return ans
    _dataFromDescriptor=staticmethod(_dataFromDescriptor)
TreeNode.mdsdtypeToClass[TreeNode.dtype_mds]=TreeNode

class TreePath(TreeNode):
    """Class to represent an MDSplus node reference (path)."""
    dtype_mds=193
    def __init__(self,path,tree=None):
        self.tree_path=str(path)
        if tree is None:
            self.tree=Tree.getActiveTree()
        else:
            self.tree=tree
        return

    def _getDescriptor(self):
      """Return a MDSplus descriptor"""
      path=_data.String(self.tree_path).value
      d=_data._Descriptor()
      d.length=len(self.tree_path)
      d.dtype=self.dtype_mds
      d.dclass=self.mdsclass
      d.pointer=_C.cast(_C.c_char_p(path),_C.c_void_p)
      d.original=path
      d.tree=self.tree
      return _data._descrWithUnitsAndError(self,d)
    descriptor=property(_getDescriptor,)

    def __str__(self):
        """Convert path to string."""
        return str(self.tree_path)

TreeNode.mdsdtypeToClass[TreePath.dtype_mds]=TreePath

class TreeNodeArray(_data.Data):
    def __eq__(self,arg):
        if not isinstance(arg,TreeNodeArray):
            raise Exception("Can compare to only another TreeNodeArray instance")
        else:
            return (self.tree==arg.tree and self.nids.value==arg.nids.value).all()

    def __len__(self):
        return self.nids.value.__len__()
    
    def __init__(self,nids,tree=None):
        self.nids=_data.Int32Array(nids)
        if tree is None:
            self.tree=Tree.getActiveTree()
        else:
            self.tree=tree

    def __getitem__(self,n):
        """Return TreeNode from mdsarray. array[n]
        @param n: Index into array beginning with index 0
        @type n: int
        @return: node
        @rtype: TreeNode
        """
        ans=TreeNode(self.nids[n],self.tree)
        return ans

    def __str__(self):
      nlist=list()
      for i in self.nids:
        nlist.append(TreeNode(i,self.tree))
      return str(nlist)

    __repr__=__str__

    def restoreContext(self):
        self.tree.restoreContext()

    def getPath(self):
        """Return StringArray of node paths
        @return: Node names
        @rtype: StringArray
        """
        return self.path

    def getFullPath(self):
        """Return StringArray of full node paths
        @return: Full node paths
        @rtype: StringArray
        """
        return self.fullpath

    def getNid(self):
        """Return nid numbers
        @return: nid numbers
        @rtype: Int32Array
        """
        return self.nids

    def isOn(self):
        """Return bool array
        @return: true if node is on
        @rtype: Int8Array
        """
        return self.on

    def setOn(self,flag):
        """Turn nodes on or off
        @param flag: True to turn nodes on, False to turn them off
        @type flag: Bool
        @rtype: None
        """
        for nid in self:
            nid.setOn(flag)

    def getLength(self):
        """Return data lengths
        @return: Array of data lengths
        @rtype: Int32Array
        """
        return self.length

    def getCompressedLength(self):
        """Return compressed data lengths
        @return: Array of compressed data lengths
        @rtype: Int32Array
        """
        return self.rlength

    def isSetup(self):
        """Return array of bool
        @return: True if setup information
        @rtype: Uint8Array
        """
        return self.setup

    def isWriteOnce(self):
        """Return array of bool
        @return: True if node is write once
        @rtype: Uint8Array
        """
        return self.write_once
    

    def setWriteOnce(self,flag):
        """Set nodes write once
        @rtype: None
        """
        for nid in self:
            nid.setWriteOnce(flag)

    def isCompressOnPut(self):
        """Is nodes set to compress on put
        @return: state of compress on put flags
        @rtype: Uint8Array
        """
        return self.compress_on_put

    def setCompressOnPut(self,flag):
        """Set compress on put flag
        @param flag: True if compress on put, False if not
        @type flag: bool
        """
        for nid in self:
            nid.setCompressOnPut(flag)

    def isNoWriteModel(self):
        """True if nodes set to no write model
        @return: True if nodes set to no write model mode
        @rtype: Uint8Array
        """
        return self.no_write_model

    def setNoWriteModel(self,flag):
        """Set no write model flag
        @param flag: True to disallow writing to model
        @type flag: bool
        """
        for nid in self:
            nid.setNoWriteModel(flag)

    def isNoWriteShot(self):
        """True if nodes are set no write shot
        @return: 1 of set no write shot
        @rtype: Uint8Array()
        """
        return self.no_write_shot

    def setNoWriteShot(self,flag):
        """set no write shot flags
        @param flag: True if setting no write shot
        @type flag: bool
        """
        for nid in self:
            nid.setNoWriteShot(flag)

    def getUsage(self):
        """Get usage of nodes
        @return: Usage
        @rtype: StringArray
        """
        a=list()
        for nid in self:
            a.append(str(nid.usage))
        return _data.makeArray(a)

    

    def __getattr__(self,name):
      ans = dict()
      for n in self:
        try:
          ans[str(n)]=eval('n.'+name)
        except:
          ans[str[n]]=None
      return ans

    def data(self):
      """Return dict object containing the data from the nodes in the array"""
      ans=dict()
      for n in self:
        try:
          ans[str(n)]=n.record
        except:
          ans[str(n)]=None
      return ans
      


    
class Device(TreeNode):
    """Used for device support classes. Provides ORIGINAL_PART_NAME, PART_NAME and Add methods and allows referencing of subnodes as conglomerate node attributes.

    Use this class as a superclass for device support classes. When creating a device support class include a class attribute called "parts"
    which describe the subnodes of your device implementation. The parts attribute should be a list or tuple of dict objects where each dict is a
    description of each subnode. The dict object should include a minimum of a 'path' key whose value is the relative path of the node (be sure to
    include the leading period or colon) and a 'type' key whose value is the usage type of the node. In addition you may optionally specify a
    'value' key whose value is the actual value to store into the node when it is first added in the tree. Instead of a 'value' key, you can
    provide a 'valueExpr' key whose value is a string which is python code to be evaluated before writing the result into the node. Use a valueExpr
    when you need to include references to other nodes in the device. Lastly the dict instance may contain an 'options' key whose values are
    node options specified as a tuple of strings. Note if you only specify one option include a trailing comma in the tuple.The "parts" attribute
    is used to implement the Add and PART_NAME and ORIGNAL_PART_NAME methods of the subclass.
    
    You can also include a part_dict class attribute consisting of a dict() instance whose keys are attribute names and whose values are nid
    offsets. If you do not provide a part_dict attribute then one will be created from the part_names attribute where the part names are converted
    to lowercase and the colons and periods are replaced with underscores. Referencing a part name will return another instance of the same
    device with that node as the node in the Device subclass instance. The Device class also supports the part_name and original_part_name
    attributes which is the same as doing devinstance.PART_NAME(None). NOTE: Device subclass names MUST BE UPPERCASE!

    Sample usage1::
    
       from MDSplus import Device,Action,Dispatch,Method

       class MYDEV(Device):
           parts=[{'path':':COMMENT','type':'text'},
                  {'path':':INIT_ACTION','type':'action',
                  'valueExpr':"Action(Dispatch(2,'CAMAC_SERVER','INIT',50,None),Method(None,'INIT',head))",
                  'options':('no_write_shot',)},
                  {'path':':STORE_ACTION','type':'action',
                  'valueExpr':"Action(Dispatch(2,'CAMAC_SERVER','STORE',50,None),Method(None,'STORE',head))",
                  'options':('no_write_shot',)},
                  {'path':'.SETTINGS','type':'structure'},
                  {'path':'.SETTINGS:KNOB1','type':'numeric'},
                  {'path':'.SIGNALS','type':'structure'},
                  {'path':'.SIGNALS:CHANNEL_1','type':'signal','options':('no_write_model','write_once')}]

           def init(self,arg):
               knob1=self.settings_knob1.record
               return 1

           def store(self,arg):
               from MDSplus import Signal
               self.signals_channel_1=Signal(32,None,42)

    Sample usage2::

       from MDSplus import Device

           parts=[{'path':':COMMENT','type':'text'},
                  {'path':':INIT_ACTION','type':'action',
                  'valueExpr':"Action(Dispatch(2,'CAMAC_SERVER','INIT',50,None),Method(None,'INIT',head))",
                  'options':('no_write_shot',)},
                  {'path':':STORE_ACTION','type':'action',
                  'valueExpr':"Action(Dispatch(2,'CAMAC_SERVER','STORE',50,None),Method(None,'STORE',head))",
                  'options':('no_write_shot',)},
                  {'path':'.SETTINGS','type':'structure'},
                  {'path':'.SETTINGS:KNOB1','type':'numeric'},
                  {'path':'.SIGNALS','type':'structure'},
                  {'path':'.SIGNALS:CHANNEL_1','type':'signal','options':('no_write_model','write_once')}]

           part_dict={'knob1':5,'chan1':7}

           def init(self,arg):
               knob1=self.knob1.record
               return 1

           def store(self,arg):
               from MDSplus import Signal
               self.chan1=Signal(32,None,42)
               
    If you need to reference attributes using computed names you can do something like::

        for i in range(16):
            self.__setattr__('signals_channel_%02d' % (i+1,),Signal(...))
    """
    
    gtkThread = None
    
    def __class_init__(cls):
        if not hasattr(cls,'initialized'):
            if hasattr(cls,'parts'):
                cls.part_names=list()
                for elt in cls.parts:
                    cls.part_names.append(elt['path'])
            if hasattr(cls,'part_names') and not hasattr(cls,'part_dict'):
                cls.part_dict=dict()
                for i in range(len(cls.part_names)):
                    try:
                        cls.part_dict[cls.part_names[i][1:].lower().replace(':','_').replace('.','_')]=i+1
                    except:
                        pass
            cls.initialized=True
    __class_init__=classmethod(__class_init__)

    def __new__(cls,node):
        """Create class instance. Initialize part_dict class attribute if necessary.
        @param node: Not used
        @type node: TreeNode
        @return: Instance of the device subclass
        @rtype: Device subclass instance
        """
        if cls.__name__ == 'Device':
            raise TypeError("Cannot create instances of Device class")
        cls.__class_init__();
        return super(Device,cls).__new__(cls)

    def __init__(self,node):
        """Initialize a Device instance
        @param node: Conglomerate node of this device
        @type node: TreeNode
        @rtype: None
        """
        try:
            self.nids=node.conglomerate_nids.nid_number
            self.head=int(self.nids[0])
        except Exception:
            self.head=node.nid
        super(Device,self).__init__(node.nid,node.tree)

    def ORIGINAL_PART_NAME(self,arg):
        """Method to return the original part name.
        Will return blank string if part_name class attribute not defined or node used to create instance is the head node or past the end of part_names tuple.
        @param arg: Not used. Placeholder for do method argument
        @type arg: Use None
        @return: Part name of this node
        @rtype: str
        """
        name = ""
        if self.nid != self.head:
            try:
                name = self.part_names[self.nid-self.head-1].upper()
            except:
                pass
        return name
    PART_NAME=ORIGINAL_PART_NAME

    def __getattr__(self,name):
        """Return TreeNode of subpart if name matches mangled node name.
        @param name: part name. Node path with colons and periods replaced by underscores.
        @type name: str
        @return: Device instance of device part
        @rtype: Device
        """
        if name == 'part_name' or name == 'original_part_name':
            return self.ORIGINAL_PART_NAME(None)
        try:
            return self.__class__(TreeNode(self.part_dict[name]+self.head,self.tree))
        except KeyError:
            return super(Device,self).__getattr__(name)

    def __setattr__(self,name,value):
        """Set value into device subnode if name matches a mangled subpart node name. Otherwise assign value to class instance attribute.
        @param name: Name of attribute or device subpart
        @type name: str
        @param value: Value of the attribute or device subpart
        @type value: varied
        @rtype: None
        """
        try:
            TreeNode(self.part_dict[name]+self.head,self.tree).record=value
        except KeyError:
            super(Device,self).__setattr__(name,value)

    def Add(cls,tree,path):
        """Used to add a device instance to an MDSplus tree.
        This method is invoked when a device is added to the tree when using utilities like mdstcl and the traverser.
        For this to work the device class name (uppercase only) and the package name must be returned in the MdsDevices tdi function.
        Also the Device subclass must include the parts attribute which is a list or tuple containing one dict instance per subnode of the device.
        The dict instance should include a 'path' key set to the relative node name path of the subnode. a 'type' key set to the usage string of
        the subnode and optionally a 'value' key or a 'valueExpr' key containing a value to initialized the node or a string containing python
        code which when evaluated during the adding of the device after the subnode has been created produces a data item to store in the node.
        And finally the dict instance can contain an 'options' key which should contain a list or tuple of strings of node attributes which will be turned
        on (i.e. write_once).
        """
        cls.__class_init__()
        _treeshr.TreeStartConglomerate(tree,len(cls.parts)+1)
        head=tree.addNode(path,'DEVICE')
        head=cls(head)
        head.record=_compound.Conglom('__python__',cls.__name__,None,"from %s import %s" % (cls.__module__[0:cls.__module__.index('.')],cls.__name__))
        head.write_once=True
        for elt in cls.parts:
            node=tree.addNode(path+elt['path'],elt['type'])
        for elt in cls.parts:
            node=tree.getNode(path+elt['path'])
            if 'value' in elt:
                node.record=elt['value']
            if 'valueExpr' in elt:
                try:
                    import MDSplus
                except:
                    pass
                node.record=eval(elt['valueExpr'])
            if 'options' in elt:
                for option in elt['options']:
                    exec('node.'+option+'=True')
        _treeshr.TreeEndConglomerate(tree)
    Add=classmethod(Add)


    def dw_setup(self,*args):
        """Bring up a glade setup interface if one exists in the same package as the one providing the device subclass

        The gtk.main() procedure must be run in a separate thread to avoid locking the main program. If this method
        is invoked via the Py() TDI function, care must be made to do unlock the python thread lock the first time
        a gtkMain thread is created. This thread unlocking has to be done in the Py TDI function after the GIL state
        has been restored. This method sets a public TDI variable, _PyReleaseThreadLock, which is inspected in the Py
        function and if defined, the Py function will release the thread lock. This locking scheme was arrived at
        after several days of trial and error and seems to work with at least Python versions 2.4 and 2.6.
        """
        try:
            from MDSplus.widgets import MDSplusWidget
            from MDSplus import Data
            from MDSplus import Int32
            import gtk.glade
            import os,gtk,inspect,gobject,threading
            import sys
            class gtkMain(threading.Thread):
                def run(self):
                    gtk.main()
            class MyOut:
                def __init__(self):
                    self.content=[]
                def write(self,string):
                    self.content.append(string)
                        
            gtk.gdk.threads_init()
            out=MyOut()
            sys.stdout = out
            sys.stderr = out
            window=gtk.glade.XML(os.path.dirname(inspect.getsourcefile(self.__class__))+os.sep+self.__class__.__name__+'.glade').get_widget(self.__class__.__name__.lower())
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            window.device_node=self
            window.set_title(window.get_title()+' - '+str(self)+' - '+str(self.tree))
            MDSplusWidget.doToAll(window,"reset")
        except Exception:
            import sys
            e=sys.exc_info()[1]
            print( e)
            raise Exception("No setup available, %s" % (str(e),))

        window.connect("destroy",self.onSetupWindowClose)
        window.show_all()
        if Device.gtkThread is None or not Device.gtkThread.isAlive():
            if Device.gtkThread is None:
                Int32(1).setTdiVar("_PyReleaseThreadLock");
            Device.gtkThread=gtkMain()
            Device.gtkThread.start()
        return 1
    DW_SETUP=dw_setup

    def onSetupWindowClose(self,window):
        import gtk
        windows=[toplevel for toplevel in gtk.window_list_toplevels()
                 if toplevel.get_property('type') == gtk.WINDOW_TOPLEVEL]
        if len(windows) == 1:
            gtk.main_quit()
            
    def waitForSetups(cls):
        Device.gtkThread.join()
    waitForSetups=classmethod(waitForSetups)


_tdi=_mimport('tdibuiltins',1)
