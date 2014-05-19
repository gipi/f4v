'''
A note from the documentation::

    Multi-byte integers shall be stored in big-endian byte order, in contrast with SWF,
    which uses little-endian byte order. For example, as a UI16 in SWF file format, the
    byte sequence that represents the number 300 (0x12C) is 0x2C 0x01; as a UI16 in F4V
    file format, the byte sequence that represents the number 300 is 0x01 0x2C.
'''
from lxml import etree
import base64
import logging
import struct
import sys
import os
import requests


stream = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s - %(filename)s:%(lineno)d - %(message)s')

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)

logger.addHandler(stream)
stream.setFormatter(formatter)

class RawDataIterator(object):
    def __init__(self, data):
        self.data = data
        self.index = 0
        self.endian = '>' if True else '<'

    def readUI2(self):
        return self._read('>')

    def readUI8(self):
        return self._read('>B', 1)

    def readUI16(self):
        return self._read('>H', 2)

    def readUI32(self):
        return self._read('>I', 4)

    def readUI64(self):
        return self._read('>Q', 8)

    def resetTo(self, index=0):
        self.index = index

    def rewind(self, offset):
        self.index -= offset

    def readNullString(self):
        null_string = ''

        while True:
            c = self.data[self.index]
            self.index += 1

            if c == '\x00':
                break


            null_string += c

        return null_string

    def read(self, size):
        start = self.index
        end   = self.index + size

        self.index = end

        return self.data[start:end]

    def remaining(self):
        return self.read(len(self.data) - self.index)

    def _read(self, pattern , size):
        start = self.index
        end   = self.index + size

        self.index = end

        return struct.unpack(pattern, self.data[start:end])[0]

class F4VBox(object):
    '''Generic format of a F4VBox.

    See "1.3 F4V box format" section
    '''
    def __init__(self, data):
        raw_data = None
        if isinstance(data, RawDataIterator):
            raw_data = data
        else:
            raw_data = RawDataIterator(data)

        self.size    = raw_data.readUI32()
        self.type    = raw_data.read(4)
        # FIXME: extended size
        #self.payload = raw_data.remaining()

        self.raw_data = raw_data

class F4VBootstrapInfoBox(F4VBox):
    def __init__(self, data):
        super(F4VBootstrapInfoBox, self).__init__(data)

        self.version             = self.raw_data.readUI8()
        # reserved and set to zero
        self.flags               = self.raw_data.read(3)
        self.boostrapInfoVersion = self.raw_data.readUI32()
        # profile, live, update, reserved
        self.boh                 = self.raw_data.read(1)
        self.timescale           = self.raw_data.readUI32()
        self.currentMediaTime    = self.raw_data.readUI64()
        self.SmpteTimeCodeOffset = self.raw_data.readUI64()
        self.movieIdentifier     = self.raw_data.readNullString()
        self.serverEntryCount    = self.raw_data.readUI8()
        self.serverEntryTable    = []

        logger.debug('found %d server entries' % self.serverEntryCount)

        for x in range(self.serverEntryCount):
            self.serverEntryTable.append(self.raw_data.readNullString())

        self.qualityEntryCount  = self.raw_data.readUI8()
        self.qualityEntryTable  = []

        logger.debug('found %d quality entries' % self.qualityEntryCount)

        for x in range(self.qualityEntryCount):
            self.qualityEntryTable.append(self.raw_data.readNullString())

        self.drmData            = self.raw_data.readNullString()
        self.metadata           = self.raw_data.readNullString()
        self.segmentRunTableCount = self.raw_data.readUI8()
        self.segmentRunTableEntries = []

        logger.debug('found %d segment run table entries' % self.segmentRunTableCount)

        for x in range(self.segmentRunTableCount):
           self.segmentRunTableEntries.append(F4VSegmentRunTableBox(self.raw_data))

        self.fragmentRunTableCount = self.raw_data.readUI8()
        self.fragmentRunTableEntries = []

        logger.debug('found %d fragment run table entries' % self.fragmentRunTableCount)

        for x in range(self.fragmentRunTableCount):
            self.fragmentRunTableEntries.append(F4VFragmentRunTableBox(self.raw_data))

class F4VSegmentRunTableBox(F4VBox):
    def __init__(self, data):
        super(F4VSegmentRunTableBox, self).__init__(data)

        self.version                    = self.raw_data.readUI8()
        self.flags                      = self.raw_data.read(3)
        self.qualityEntryCount          = self.raw_data.readUI8()
        self.qualitySegmentURLModifiers = []

        for x in range(self.qualityEntryCount):
            self.qualitySegmentURLModifiers.append(self.raw_data.readNullString())

        self.segmentRunEntryCount       = self.raw_data.readUI32()
        self.segmentRunEntryTable       = []

        logger.debug('found %d segment run entries' % self.segmentRunEntryCount)

        for x in range(self.segmentRunEntryCount):
            first_segment = self.raw_data.readUI32()
            fragments_per_segment = self.raw_data.readUI32()

            entry = {
                'first_segment': first_segment,
                'fragments_per_segment': fragments_per_segment,
            }

            logger.debug(entry)
            self.segmentRunEntryTable.append(entry)

class F4VFragmentRunTableBox(F4VBox):
    def __init__(self, data):
        super(F4VFragmentRunTableBox, self).__init__(data)

        self.version = self.raw_data.readUI8()
        self.flags   = self.raw_data.read(3)
        self.timeScale = self.raw_data.readUI32()
        self.qualityEntryCount = self.raw_data.readUI8()
        self.qualitySegmentURLModifiers = []

        for x in range(self.qualityEntryCount):
            self.qualitySegmentURLModifiers.append(self.raw_data.readNullString())

        self.fragmentRunEntryCount = self.raw_data.readUI32()
        self.fragmentRunEntryTable = []

        for x in range(self.fragmentRunEntryCount):
            d = {}
            d['first_fragment'] = self.raw_data.readUI32()
            d['first_fragment_timestamp'] = self.raw_data.readUI64()
            d['fragment_duration'] = self.raw_data.readUI32()
            d['discontinuity_indicator'] =  self.raw_data.readUI8() if d['fragment_duration'] == 0 else None,
            logger.debug(d)

            self.fragmentRunEntryTable.append(d)

class Manifest(object):
    '''Parse the manifest file'''
    ADOBE_NS = 'http://ns.adobe.com/f4m/1.0'
    ADOBE_NSS = {'namespaces': {'adobe': ADOBE_NS}}
    def __init__(self, filepath=None, base_url=None):
        logger.info('loading data from %s' % filepath)
        manifest_tree = etree.parse(filepath)

        bootstrapInfoNodes = self._get_from_xpath(manifest_tree, '//adobe:manifest/adobe:bootstrapInfo')
        if len(bootstrapInfoNodes) > 0:
            self.bootstrapBox = F4VBootstrapInfoBox(base64.b64decode(bootstrapInfoNodes[0].text))

        baseURL = self._get_from_xpath(manifest_tree, '//adobe:manifest/adobe:baseURL')

        self.baseURL = baseURL if baseURL else base_url

        medias = self._get_from_xpath(manifest_tree, '//adobe:manifest/adobe:media')
        self.medias = []

        def __get_attr(node, attr):
            return node.attrib[attr] if node.attrib.has_key(attr) else None

        for m in medias:
            media_attr = {
                'url':             __get_attr(m, 'url'),
                'bitrate':         __get_attr(m, 'bitrate'),
                'width':           __get_attr(m, 'width'),
                'height':          __get_attr(m, 'height'),
                'bootstrapInfoId': __get_attr(m, 'bootstrapInfoId'),
                # FIXME: add missing info
            }
            logger.debug('found media: %s' % media_attr)
            self.medias.append(media_attr)

    def _get_from_xpath(self, tree, xpath):
        return tree.xpath(xpath, **self.ADOBE_NSS)

    def getUrl(self, segment, fragment):
        return 'http://%s/%s%sSeg%d-Frag%d' % (
            self.baseURL,
            self.id,
            "", # quality segment url modifier
            segment,
            fragment,
        )

def usage(progname):
    print('usage: %s <manifest>' % progname)
    sys.exit(0)

def downloadManifest(url):
    r = requests.get(url)
    if r.status_code != 200:
        raise AttributeError()

    local_filename = 'manifest.f4m'

    with open(local_filename, 'w') as f:
        f.write(r.text)

    return local_filename, os.path.dirname(url)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        usage(sys.argv[0])

    manifestPath = sys.argv[1]

    manifestPath, base_url = (manifestPath, None) if not manifestPath.startswith('http:') else downloadManifest(manifestPath)

    manifest = Manifest(filepath=manifestPath, base_url=base_url)
