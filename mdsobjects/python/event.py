import numpy as _NP
import ctypes as _C
import sys as _sys
import time as _time
from threading import Thread as _Thread
if _sys.version_info[0] >= 3:
  buffer=memoryview

if '__package__' not in globals() or __package__ is None or len(__package__)==0:
  def _mimport(name,level):
    return __import__(name,globals())
else:
  def _mimport(name,level):
    return __import__(name,globals(),{},[],level)

_data=_mimport('data',1)

class MdsTimeout(Exception):
  pass

class MdsNoMoreEvents(Exception):
  pass

class MdsInvalidEvent(Exception):
  pass

_MdsShr=_data._loadLib('MdsShr')

def DateToQuad(date):
    ans=_C.c_ulonglong(0)
    status = _MdsShr.LibConvertDateString(_C.c_char_p(str.encode(date)),_C.pointer(ans))
    if not (status & 1):
        raise MdsException("Cannot parse %s as date. Use dd-mon-yyyy hh:mm:ss.hh format or \"now\",\"today\",\"yesterday\"." % (date,))
    return _data.makeData(_NP.uint64(ans.value))

def MDSWfeventTimed(event,timeout=None):
    if timeout is None:
      timeout=0
    buff=_NP.uint8(0).repeat(repeats=4096)
    numbytes=_C.c_int32(0)
    status=_MdsShr.MDSWfeventTimed(_C.c_char_p(str.encode(event)),_C.c_int32(len(buff)),
                                   buff.ctypes.data,_C.pointer(numbytes),_C.c_int32(timeout))
    if (status & 1) == 1:
        if numbytes.value == 0:
          return _data.Uint8Array([])
        else:
          return _data.makeArray(buff[0:numbytes.value])
    elif (status == 0):
        raise MdsTimeout("Event %s timed out." % (str(event),))
    else:
        raise MdsException(_data.getStatusMsg(status))

def MDSEvent(event,uint8_array):
    status=_MdsShr.MDSEvent(_C.c_char_p(str.encode(event)),_C.c_int32(len(uint8_array)),uint8_array.ctypes.data)
    if not ((status & 1) == 1):
        raise MdsException(_data.getStatusMsg(status))
 
class Event(_Thread):
    """Thread to wait for event"""

    def getData(self):
        """Return data transfered with the event.
        @rtype: Data
        """
        if len(self.raw) == 0:
            return None
        return _data.makeArray(self.getRaw()).deserialize()

    def getRaw(self):
        """Return raw data transfered with the event.
        @rtype: numpy.uint8
        """
        if len(self.raw) == 0:
            return None
        return self.raw

    def getTime(self):
        """Return time of event in seconds since epoch
        rtype: float
        """
        return self.time

    def getQTime(self):
        """Return quadword time when the event last occurred
        rtype: Uint64
        """
        return self.qtime
        
    def getName(self):
        """Return the name of the event
        rtype: str
        """
        return self.event

    def setevent(event,data=None):
        """Issue an MDSplus event
        @param event: event name
        @type event: str
        @param data: data to pass with event
        @type data: Data
        """
        if data is None:
            Event.seteventRaw(event,None)
        else:
            Event.seteventRaw(event,makeData(data).serialize())
    setevent=staticmethod(setevent)

    def seteventRaw(event,buffer=None):
        """Issue an MDSplus event
        @param event: event name
        @type event: str
        @param buffer: data buffer
        @type buffer: numpy.uint8 array
        """
        if buffer is None:
            buffer=_NP.array([])
        MDSEvent(event,buffer)
    seteventRaw=staticmethod(seteventRaw)

    def wfevent(event,timeout=0):
        """Wait for an event
        @param event: event name
        @rtype: Data
        """
        return MDSWfeventTimed(event,timeout).deserialize()
    wfevent=staticmethod(wfevent)


    def wfeventRaw(event,timeout=0):
        """Wait for an event
        @param event: event name
        @rtype: Data
        """
        return MDSWfeventTimed(event,timeout)
    wfeventRaw=staticmethod(wfeventRaw)

    def queueEvent(event):
        """Establish an event queue for an MDSplus event. Event occurrences will be monitored and accumulate
        until calls to MDSGetEventQueue retrieves the events occurences.
        @param event: Name of event to monitor
        @type event: str
        @return: eventid used in MDSGetEventQueue, and MDSEventCan
        @rtype: int
        """
        eventid=_C.c_int32(0)
        status = _MdsShr.MDSQueueEvent(_C.c_char_p(str.encode(event)),_C.pointer(eventid))
        if status&1 == 1:
            return eventid.value
        else:
            raise MdsException("Error queuing the event %s : " % (event,_data.getStatusMsg(status)))
    queueEvent=staticmethod(queueEvent)

    def getQueue(eventid,timeout=0):
        """Retrieve event occurrence.
        @param eventid: eventid returned from MDSQueueEvent function
        @type eventid: int
        @param timeout: Optional timeout. If greater than 0 an MdsTimeout exception will be raised if no event occurs
        within timeout seconds after function invokation. If timeout equals zero then this function will
        block until an event occurs. If timeout is less than zero this function will not wait for events
        and will either returned a queued event or raise MdsNoMoreEvents.
        @type timeout: int
        @return: event data
        @rtype: Uint8Array
        """
        dlen=_C.c_int32(0)
        bptr=_C.c_void_p(0)
        status=_MdsShr.MDSGetEventQueue(_C.c_int32(eventid),_C.c_int32(timeout),_C.pointer(dlen),_C.pointer(bptr))
        if status==1:
            if dlen.value>0:
                ans = _data.Uint8Array(_NP.ndarray(shape=[dlen.value],buffer=buffer(_C.cast(bptr,_C.POINTER((_C.c_uint8 * dlen.value))).contents),dtype=_NP.uint8))
                _MdsShr.MdsFree(bptr)
                return ans
            else:
                return _data.Uint8Array([])
        elif status==0:
            if timeout > 0:
                raise MdsTimeout("Timeout")
            else:
                raise MdsNoMoreEvents("No more events")
        elif status==2:
            raise MdsInvalidEvent("Invalid eventid")
        else:
            raise MdsException("Unknown error - status=%d" % (status,))
    getQueue=staticmethod(getQueue)

    def eventCan(eventid):
      """Cancel a queued event
      @param eventid: eventid returned from queueEvent function
      @type eventid: int
      """
      _MdsShr.MDSEventCan(_C.c_int32(eventid))

    def _event_run(self):
        while True:
            try:
                self.raw=self.getQueue(self.eventid,self.timeout)
                self.exception=None
            except MdsInvalidEvent:
                return
            except Exception:
                self.exception=_sys.exc_info()[1]
            self.time=_time.time()
            self.qtime=DateToQuad("now")
            self.subclass_run()
            _time.sleep(.01)

    def cancel(self):
        """Cancel this event instance. No further events will be processed for this instance.
        """
        self.eventCan(self.eventid)

    def __init__(self,event,timeout=0):
        """Saves event name and starts wfevent thread
        @param event: name of event to monitor
        @type event: str
        """
        super(Event,self).__init__()
        self.event=event
        self.exception=None
        self.timeout=timeout
        self.eventid=self.queueEvent(event)
        self.subclass_run=self.run
        self.run=self._event_run
        self.setDaemon(True)
        self.raw=None
        self.time=None
        self.start()
 
