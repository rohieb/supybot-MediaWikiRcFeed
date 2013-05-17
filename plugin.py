import supybot.callbacks as callbacks
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import time
import urllib
from xml.dom.minidom import parse
from collections import deque
#from supybot.commands import wrap


class MediaWikiRcFeed(callbacks.Plugin):
  """
  This plugin feeds the recent changes of a MediaWiki instance to IRC.
  """

  class RcItem:
    """container for recent change items"""
    def __init__(self, rcType=None, rcId=None, title=None, user=None,
      timestamp=None, oldRev=None, newRev=None, comment=None, minor=None):
      
      self.type = rcType
      self.id = rcId
      self.title = title
      self.user = user
      self.timestamp = timestamp
      self.oldRev = oldRev
      self.newRev = newRev
      self.comment = comment
      self.minor = minor
      
    def __repr__(self):
      return ("RcItem(self=%s, type=%r, id=%r, title=%r, user=%r, timestamp=%r,"
        " oldRev=%r, newRev=%r, comment=%r, minor=%r)") % (id(self), self.type, 
        self.id, self.title, self.user, self.timestamp, self.oldRev, 
        self.newRev, self.comment, self.minor)

  class LogItem:
    """container for log items"""
    def __init__(self, logType=None, action=None, logId=None, pageTitle=None,
      user=None, timestamp=None, comment=None, params=None):
      
      self.type = logType
      self.action = action
      self.id = logId
      self.title = pageTitle
      self.user = user
      self.timestamp = timestamp
      self.comment = comment
      self.params = params

    def __repr__(self):
      return ("LogItem(self=%s, type=%r, action=%r, id=%r, title=%r, user=%r, "
        "timestamp=%r, comment=%r, params=%r)") % (id(self), self.type, 
        self.action, self.id, self.title, self.user, self.timestamp, 
        self.comment, self.params)

  threaded = True
  rcQueryUrl = ("%s/api.php?action=query&list=recentchanges&rcprop=title|user|"
    "ids|comment|flags|timestamp&rcshow=!bot&format=xml&"
    "rcnamespace=0|1|2|3|4|5|6|7")
  logQueryUrl = "%s/api.php?action=query&list=logevents&format=xml"
  
  def __init__(self, irc):
    self.__parent = super(MediaWikiRcFeed, self)
    self.__parent.__init__(irc)

    #self.log.info("MediaWikiRcFeed: begin __init__") ############ FIXME

    self.baseurl = "https://stratum0.org/mediawiki".rstrip("/") # FIXME: from config
    #self.baseurl = "http://commons.wikimedia.org/w".rstrip("/") # FIXME: from config
    #self.baseurl = "http://de.wikipedia.org/w".rstrip("/") # FIXME: from config
    self.lastRcId = 0
    self.lastLogId = 0
    self.lastCalled = int(time.time())
    # get latest item and log IDs
    dom = self.loadDom(self.rcQueryUrl % self.baseurl)
    self.lastRcId = self.parseRcItem(dom.getElementsByTagName("rc")[0]).id
    dom = self.loadDom(self.logQueryUrl % self.baseurl)
    self.lastLogId = self.parseLogItem(dom.getElementsByTagName("item")[0]).id
    
    #self.log.info("MediaWikiRcFeed: end __init__: lastRc %d, lastLog %d" % \
    #  (self.lastRcId, self.lastLogId)) ############ FIXME
    
  def __call__(self, irc, msg):
    #self.log.info("MediaWikiRcFeed: lastCalled is %r, time is %r" %
    #  (self.lastCalled, int(time.time())))
    if self.lastCalled + 10 < int(time.time()):  #### FIXME time from config
      #self.log.info("MediaWikiRcFeed: __call__ called")
      items = self.getItems(True)
      items.extend(self.getItems(False))
      items.sort(key=lambda x: x.timestamp)
      self.printItems(irc, items)
      self.lastCalled = int(time.time())
    else:
      #self.log.info("MediaWikiRcFeed: not calling __call__")
      pass

  def loadDom(self, url):
    """load URL and return DOM object"""
    #self.log.info("MediaWikiRcFeed: Fetching " + url)
    f = urllib.urlopen(url)
    return parse(f)

  def parseRcItem(self, item):
    """parse a <item> DOM item and return a RcItem object"""
    rcid = int(item.getAttribute("rcid"))
    if rcid > self.lastRcId:
      #self.log.info("found id: %d" % rcid)
      return self.RcItem(item.getAttribute("type"), rcid,
        item.getAttribute("title"),
        item.getAttribute("user"), 
        item.getAttribute("timestamp"), int(item.getAttribute("old_revid")),
        int(item.getAttribute("revid")),
        item.getAttribute("comment"),
        True if item.hasAttribute("minor") else False)
    else:
      #self.log.info("ignoring id %s: too small" % rcid)
      return None
  
  def parseLogItem(self, le):
    """parse an <item> DOM item and return a LogItem object"""
    logid = int(le.getAttribute("logid"))
    if logid > self.lastLogId:
      #self.log.info("found id: %s" % logid)

      params = {}
      if le.getElementsByTagName("block"):
        block = le.getElementsByTagName("block")[0]
        params = { "flags" : block.getAttribute("flags"),
          "duration": block.getAttribute("duration"),
          "expiry": block.getAttribute("expiry") }
      elif le.getElementsByTagName("param"):
        params = le.getElementsByTagName("param")[0].childNodes[0].data
      elif le.getElementsByTagName("move"):
        params = le.getElementsByTagName("move")[0].getAttribute("new_title")
      
      return self.LogItem(le.getAttribute("type"), le.getAttribute("action"), 
        logid, le.getAttribute("title"),
        le.getAttribute("user"), le.getAttribute("timestamp"),
        le.getAttribute("comment"), params)
    else:
      #self.log.info("ignoring id %s: too small" % le.getAttribute("logid"))
      return None;
  
  def getItems(self, loadRc=False, start=None):
    """get recent change (loadRc=True) or log event (loadRc=False) items from
       API and return list of RcItem objects"""
    if loadRc:
      #self.log.info("getItems: load recent changes")
      url = self.rcQueryUrl % self.baseurl
      lastItemId = self.lastRcId
      urlStartParam = "rcstart"
      qcTagName = "recentchanges"
      itemTagName = "rc"
    else:
      #self.log.info("getItems: load log events")
      url = self.logQueryUrl % self.baseurl
      lastItemId = self.lastLogId
      urlStartParam = "lestart"
      qcTagName = "logevents"
      itemTagName = "item"
      
    if start:
      url += "&%s=%s" % (urlStartParam, start)
    
    dom = self.loadDom(url)
    
    # parse items and stuff them into array
    ret = []
    for item in dom.getElementsByTagName(itemTagName):
      if loadRc:
        pi = self.parseRcItem(item)
      else:
        pi = self.parseLogItem(item)
      if(pi):   # prevent insertion of None's
        ret.append(pi)
    #self.log.info("array: %r" % ret)
    
    # continue until we have found the last recent ID
    qc = dom.getElementsByTagName("query-continue")
    if len(ret) > 0:
      lastCurId = ret[-1].id
      if lastCurId > lastItemId + 1 and qc != None and len(qc) > 0:
        qcTn = qc[0].getElementsByTagName(qcTagName)
        if qcTn != None and len(qcTn) > 0:
          qcTnStart = qcTn[0].getAttribute(urlStartParam)
          if qcTnStart:
            #self.log.info("following query-continue") ## FIXME
            ret.extend(self.getItems(loadRc, qcTnStart))
      if loadRc:
        self.lastRcId = ret[0].id
      else:
        self.lastLogId = ret[0].id
        
    #self.log.info("lastItemId after query: %s" % lastItemId) #### FIXME
    
    return ret

  def mwUrlTitleEncode(self, s):
    """urlencode only the special characters in a MediaWiki page title, but 
    let other characters untouched for better readability"""
    s = s.replace(" ","_")
    s = s.replace("~","%7E")
    s = s.replace("&","%26")
    s = s.replace("#","%23")
    s = s.replace("?","%3F")
    s = s.replace("(","%28")  # prevents some clients to detect the whole URL
    s = s.replace(")","%29")  # smae
    return s
  
  def printItems(self, irc, items):
    """print parsed messages to IRC"""
        
    prefix = "" #"RC: " # FIXME from config
    #queryMax = 10 # FIXME from config

    #self.log.info("printItems called")  ### FIXME
    items = deque(items)
    while len(items) > 0:
      item = items.popleft()
      if isinstance(item, self.RcItem):
        msg = self.formatRcItem(item)
      else:
        msg = self.formatLogItem(item)
      if msg and len(msg):
        msg = "%s%s" % (prefix, msg)
        ### FIXME CHANGE CHANNEL
        irc.queueMsg(ircmsgs.privmsg("#stratum0", msg.encode("utf-8")))
      else:
        #self.log.info("Message munched: %r" % msg)
        pass

  def formatRcItem(self, item):
    """format a recent change item"""
    if item.type == "log":
      return None   # let printLogItem do the work
    else:
      # content changes
      flagStr = "";
      if item.type == "new":
        flagStr += "N"
      if item.minor:
        #flagStr += "M"
        self.log.info("minor edit munched");
        return None;   # don't print minor changes
      if len(flagStr):
        flags = " [%s]" % ircutils.bold(flagStr.upper())
      else:
        flags = ""
        
      comment = ' (%s)' % item.comment.strip() if len(item.comment) else ""
      ##### FIXME remove timestamp
      return 'Page %s changed by %s%s%s <%s/index.php?diff=%d&oldid=%d>' % \
        (ircutils.bold(item.title), ircutils.bold(item.user), flags, comment,
        self.baseurl, item.newRev, item.oldRev)
      #self.log.info(msg) # FIXME

  def formatLogItem(self, item):
    """format a log event item"""

    comment = ' (%s)' % item.comment.strip() if item.comment and \
      len(item.comment.strip()) else ""

    if item.type == "delete":
      if item.comment.startswith("Unpassender Inhalt (Werbung, etc.)"):
        #self.log.info("delete-spam munched")
        return None
      if item.action == "revision":
        item.action = "revision delete"

      return 'Page %sd %s by %s%s' % (item.action, ircutils.bold(item.title),
        ircutils.bold(item.user), comment)
    
    elif item.type == "block":
      if item.action == "unblock":
        return '%s unblocked %s%s <%s/index.php?title=%s>' % \
        (ircutils.bold(item.user), ircutils.bold(item.title), comment, 
        self.baseurl, self.mwUrlTitleEncode(item.title))
      else:
        if item.comment.startswith("Einstellen unsinniger Inhalte in Seiten"):
          #self.log.info("block-spam munched")
          return None

        timespan = item.params["duration"]
        timespan = "an infinite time" if "infinite" in item.params["duration"] \
          else item.params["duration"]
        flags = ", no account creation" if "nocreate" in item.params["flags"] \
          else ""
        return '%s blocked %s for %s%s%s <%s/index.php?title=%s>' % \
          (ircutils.bold(item.user), ircutils.bold(item.title), timespan, 
          flags, comment, self.baseurl, self.mwUrlTitleEncode(item.title))
    
    elif item.type == "newusers":
      return 'New user account %s created by %s' % \
        (ircutils.bold(item.title), ircutils.bold(item.user)) 
    
    elif item.type == "protect":
      if item.action == "unprotect":
        return "%s unprotected %s%s <%s/index.php?title=%s>" % \
          (ircutils.bold(item.user), ircutils.bold(item.title), comment,
          self.baseurl, self.mwUrlTitleEncode(item.title))
      else:
        return ("%s changed the protection of %s to %s%s <%s/index.php?"
          "title=%s>") % (ircutils.bold(item.user), ircutils.bold(item.title),
          item.params, comment, self.baseurl, self.mwUrlTitleEncode(item.title))
    
    elif item.type == "move":
      return "Page %s moved to %s by %s%s <%s/index.php?title=%s>" % \
        (ircutils.bold(item.title), ircutils.bold(item.params), 
        ircutils.bold(item.user), comment, self.baseurl,
        self.mwUrlTitleEncode(item.params))
    
    elif item.type == "upload":
      return "%s uploaded %s <%s/index.php?title=%s>" % \
        (ircutils.bold(item.user), ircutils.bold(item.title), self.baseurl,
        self.mwUrlTitleEncode(item.title))

    elif item.type == "patrol":
      pass  # not interesting
    elif item.type == "review":
      pass  # not interesting
    else:
      self.log.info(("MediaWikiParseRc.formatLogItem(): Oops. It seems I don't "
        "know how to format this log event: %r") % item)
      return None # we don't know what to do here

Class = MediaWikiRcFeed

#rf = MediaWikiRcFeed(None)
#rf.printRcItems(None)

# vim:set shiftwidth=2 tabstop=2 expandtab textwidth=80 :
