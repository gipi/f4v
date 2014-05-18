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


stream = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s - %(filename)s:%(lineno)d - %(message)s')

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)

logger.addHandler(stream)
stream.setFormatter(formatter)


class F4VBox(object):
    '''Generic format of a F4VBox.

    See "1.3 F4V box format" section
    '''
    def __init__(self, data):
        # big endian unsigned integer
        self.size    = struct.unpack('>I', data[:4])
        self.type    = data[4:8]
        self.payload = data[8:]

class Manifest(object):
    '''Parse the manifest file'''
    ADOBE_NS = 'http://ns.adobe.com/f4m/1.0'
    ADOBE_NSS = {'namespaces': {'adobe': ADOBE_NS}}
    def __init__(self, filepath=None):
        logger.info('loading data from %s' % filepath)
        manifest_tree = etree.parse(filepath)

        bootstrapInfoNodes = self._get_from_xpath(manifest_tree, '//adobe:manifest/adobe:bootstrapInfo')
        if len(bootstrapInfoNodes) > 0:
            self.bootstrapBox = F4VBox(base64.b64decode(bootstrapInfoNodes[0].text))

        baseURL = self._get_from_xpath(manifest_tree, '//adobe:manifest/adobe:baseURL')

        self.baseURL = baseURL[0] if len(baseURL) > 0 else 'miao'

    def _get_from_xpath(self, tree, xpath):
        return tree.xpath(xpath, **self.ADOBE_NSS)


if __name__ == '__main__':
    import sys
    manifest = Manifest(filepath=sys.argv[1])

