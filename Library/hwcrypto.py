import logging
import os

from Library.utils import LogBase
from Library.hwcrypto_gcpu import GCpu
from Library.hwcrypto_dxcc import dxcc
from Library.hwcrypto_sej import sej
from Library.cqdma import cqdma

class crypto_setup:
    hwcode = None
    dxcc_base = None
    gcpu_base = None
    da_payload_addr = None
    sej_base = None
    read32 = None
    write32 = None
    writemem = None
    blacklist = None
    cqdma_base = None
    ap_dma_mem = None

class hwcrypto(metaclass=LogBase):
    def __init__(self, setup, loglevel=logging.INFO):
        self.__logger = self.__logger
        self.info = self.__logger.info
        self.debug = self.__logger.debug
        self.error = self.__logger.error
        self.warning = self.__logger.warning
        if loglevel == logging.DEBUG:
            logfilename = os.path.join("logs", "log.txt")
            if os.path.exists(logfilename):
                os.remove(logfilename)
            fh = logging.FileHandler(logfilename)
            self.__logger.addHandler(fh)
            self.__logger.setLevel(logging.DEBUG)
        else:
            self.__logger.setLevel(logging.INFO)

        self.dxcc = dxcc(setup, loglevel)
        self.gcpu = GCpu(setup, loglevel)
        self.sej = sej(setup, loglevel)
        self.cqdma = cqdma(setup, loglevel)
        self.hwcode = setup.hwcode
        self.setup = setup

    def aes_hwcrypt(self, data, iv=None, encrypt=True, mode="cbc", btype="sej"):
        if btype == "sej":
            if encrypt:
                if mode == "cbc":
                    return self.sej.hw_aes128_cbc_encrypt(buf=data, encrypt=True)
            else:
                if mode == "cbc":
                    return self.sej.hw_aes128_cbc_encrypt(buf=data, encrypt=False)
        elif btype == "gcpu":
            addr = self.setup.da_payload_addr
            if mode == "ebc":
                return self.gcpu.aes_read_ebc(data=data, encrypt=encrypt)
            if mode == "cbc":
                if self.gcpu.aes_setup_cbc(addr=addr, data=data, iv=iv, encrypt=encrypt):
                    return self.gcpu.aes_read_cbc(addr=addr, encrypt=encrypt)
        elif btype == "dxcc":
            if mode == "fde":
                return self.dxcc.generate_fde()
            elif mode == "rpmb":
                return self.dxcc.generate_rpmb()
            elif mode == "t-fde":
                return self.dxcc.generate_trustonic_fde()
        else:
            self.error("Unknown aes_hwcrypt type: " + btype)
            self.error("aes_hwcrypt supported types are: sej")
            return bytearray()

    def disable_range_blacklist(self, btype, refreshcache):
        if btype == "gcpu":
            self.info("GCPU Init Crypto Engine")
            self.gcpu.init()
            self.gcpu.acquire()
            self.gcpu.init()
            self.gcpu.acquire()
            self.info("Disable Caches")
            refreshcache(0xB1)
            self.info("GCPU Disable Range Blacklist")
            self.gcpu.disable_range_blacklist()
        elif btype == "cqdma":
            self.info("Disable Caches")
            refreshcache(0xB1)
            self.info("CQDMA Disable Range Blacklist")
            self.cqdma.disable_range_blacklist()
