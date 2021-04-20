#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2021 MIT License
import logging, os
from struct import pack
from Library.utils import LogBase

regval = {
    "DXCC_CON": 0x0000,
}

class dxcc_reg:
    def __init__(self, setup):
        self.dxcc_base = setup.dxcc_base
        self.read32 = setup.read32
        self.write32 = setup.write32

    def __setattr__(self, key, value):
        if key in ("sej_base", "read32", "write32", "regval"):
            return super(dxcc_reg, self).__setattr__(key, value)
        if key in regval:
            addr = regval[key] + self.sej_base
            return self.write32(addr, value)
        else:
            return super(dxcc_reg, self).__setattr__(key, value)

    def __getattribute__(self, item):
        if item in ("sej_base", "read32", "write32", "regval"):
            return super(dxcc_reg, self).__getattribute__(item)
        if item in regval:
            addr = regval[item] + self.sej_base
            return self.read32(addr)
        else:
            return super(dxcc_reg, self).__getattribute__(item)


class dxcc(metaclass=LogBase):
    rpmb_ikey = b"RPMB KEY"
    rpmb_salt = b"SASI"
    fde_ikey = b"SQNC!LFZ"
    fde_salt = b"TBTJ"

    DX_HOST_IRR = 0xA00
    DX_HOST_ICR = 0xA08  # DX_CC_REG_OFFSET(HOST_RGF, HOST_ICR)
    DX_DSCRPTR_QUEUE0_WORD0 = 0xE80
    DX_DSCRPTR_QUEUE0_WORD1 = 0xE84
    DX_DSCRPTR_QUEUE0_WORD2 = 0xE88
    DX_DSCRPTR_QUEUE0_WORD3 = 0xE8C
    DX_DSCRPTR_QUEUE0_WORD4 = 0xE90
    DX_DSCRPTR_QUEUE0_WORD5 = 0xE94
    DX_DSCRPTR_QUEUE0_CONTENT = 0xE9C
    DX_HOST_SEP_HOST_GPR4 = 0xAA0

    def SB_HalClearInterruptBit(self):
        self.write32(self.dxcc_base + self.DX_HOST_ICR, [4])

    def SB_CryptoWait(self):
        while True:
            value = self.read32(self.dxcc_base + self.DX_HOST_IRR)
            if value != 0:
                return value
        return None

    def SaSi_PalDmaUnMap(self, value1):
        return

    def SaSi_PalDmaMap(self, value1):
        # value2=value1
        return value1

    def SaSi_SB_AddDescSequence(self, data):
        while True:
            if self.read32(self.dxcc_base + self.DX_DSCRPTR_QUEUE0_CONTENT) << 0x1C != 0:
                break
        self.write32(self.dxcc_base + self.DX_DSCRPTR_QUEUE0_WORD0, data[0])
        self.write32(self.dxcc_base + self.DX_DSCRPTR_QUEUE0_WORD1, data[1])
        self.write32(self.dxcc_base + self.DX_DSCRPTR_QUEUE0_WORD2, data[2])
        self.write32(self.dxcc_base + self.DX_DSCRPTR_QUEUE0_WORD3, data[3])
        self.write32(self.dxcc_base + self.DX_DSCRPTR_QUEUE0_WORD4, data[4])
        self.write32(self.dxcc_base + self.DX_DSCRPTR_QUEUE0_WORD5, data[5])

    def __init__(self, setup, loglevel=logging.INFO):
        self.hwcode = setup.hwcode
        self.dxcc_base = setup.dxcc_base
        self.read32 = setup.read32
        self.write32 = setup.write32
        self.writemem = setup.writemem
        self.da_payload_addr = setup.da_payload_addr

        self.__logger = self.__logger
        self.reg = dxcc_reg(setup)

        self.info = self.__logger.info
        if loglevel == logging.DEBUG:
            logfilename = os.path.join("logs", "log.txt")
            if os.path.exists(logfilename):
                os.remove(logfilename)
            fh = logging.FileHandler(logfilename)
            self.__logger.addHandler(fh)
            self.__logger.setLevel(logging.DEBUG)
        else:
            self.__logger.setLevel(logging.INFO)

    def tzcc_clk(self, value):
        if value:
            res = self.write32(0x1000108C, 0x18000000)
        else:
            res = self.write32(0x10001088, 0x8000000)
        return res

    def generate_fde(self):
        self.tzcc_clk(1)
        dstaddr=self.da_payload_addr - 0x300
        fdekey = self.SBROM_KeyDerivation(1, self.fde_ikey, self.fde_salt, 0x10, dstaddr)
        self.tzcc_clk(0)
        return fdekey

    def generate_trustonic_fde(self, key_sz=32):
        fdekey = b""
        dstaddr = self.da_payload_addr - 0x300
        for ctr in range(0, key_sz // 16):
            self.tzcc_clk(1)
            trustonic = b"TrustedCorekeymaster" + b'\x07' * 0x10
            seed = trustonic + pack("<B", ctr)
            fdekey += self.SBROM_KeyDerivation(1, b"", seed, 0x10, dstaddr)
            self.tzcc_clk(0)
        return fdekey

    def generate_rpmb(self):
        self.tzcc_clk(1)
        dstaddr = self.da_payload_addr - 0x300
        rpmbkey = self.SBROM_KeyDerivation(1, self.rpmb_ikey, self.rpmb_salt, 0x20, dstaddr)
        self.tzcc_clk(0)
        return rpmbkey

    # SBROM_KeyDerivation(dxcc_base,encmode=1,fde1,8,fde2,4,fdekey,fdekey>>31,fdekeylen
    """
    SBROM_KeyDerivation PC(00230B77) R0:10210000,R1:00000001,R2:001209D8,R3:00000008,R4:00100000,R5:00233760,R6:00000010
    R2:53514e43214c465a
    R5:52504d42204b45595341534953514e43
    key="SQNC!LFZ",8
    salt="SASI",4
    requestedlen=0x10
    """

    def SBROM_KeyDerivation(self, encmode, key, salt, requestedlen, destaddr):
        result = bytearray()
        buffer = bytearray(b"\x00" * 0x43)
        if encmode - 1 > 4 or (1 << (encmode - 1) & 0x17) == 0:
            return 0xF2000002
        if requestedlen > 0xFF or (requestedlen << 28) & 0xFFFFFFFF:
            return 0xF2000003
        if 0x0 >= len(key) > 0x20:
            return 0xF2000003
        bufferlen = len(salt) + 3 + len(key)
        iterlength = (requestedlen + 0xF) >> 4
        if len(key) == 0:
            keyend = 1
        else:
            buffer[1:1 + len(key)] = key
            keyend = len(key) + 1
        saltstart = keyend + 1
        if len(salt) > 0:
            buffer[saltstart:saltstart + len(salt)] = salt
        # ToDo: verify buffer structure
        buffer[saltstart + len(salt):saltstart+len(salt)+4] = pack("<I",8 * requestedlen)
        # buffer=0153514e43214c465a005442544a80
        for i in range(0, iterlength):
            buffer[0] = i + 1
            dstaddr = self.SBROM_AesCmac(encmode, 0x0, buffer, 0, bufferlen, destaddr)
            if dstaddr != 0:
                for field in self.read32(dstaddr + 0x108, 4):
                    result.extend(pack("<I", field))
        return result

    def SBROM_AesCmac(self, encmode, salt, buffer, flag, bufferlen, destaddr):
        saltptr2 = 0
        dataptr2 = 0
        dataptr = destaddr + 0x118  # SP - 0xA8 - 0x24 - 0x28 - 0x38 - 0x88 - 0x30 - ((12 * 8) - 16)
        saltptr = dataptr - 0x10
        destptr = saltptr - 0x108
        self.writemem(dataptr, buffer[:bufferlen])
        self.writemem(saltptr, pack("<Q", salt))
        if self.SBROM_AesCmacDriver(encmode, saltptr, saltptr2, dataptr, dataptr2, destptr, bufferlen):
            return destptr
        return 0

    def SB_HalInit(self):
        return self.SB_HalClearInterruptBit()

    def SB_HalWaitDescCompletion(self, destptr):
        data = []
        self.SB_HalClearInterruptBit()
        val = self.SaSi_PalDmaMap(0)
        data.append(0x0)  # 0
        data.append(0x8000011)  # 1 #DIN_DMA|DOUT_DMA|DIN_CONST
        data.append(destptr)  # 2
        data.append(0x8000012)  # 3
        data.append(0x100)  # 4
        data.append((destptr >> 32) << 16)  # 5
        self.SaSi_SB_AddDescSequence(data)
        while True:
            if self.SB_CryptoWait() & 4 != 0:
                break
        while True:
            value = self.read32(self.dxcc_base + 0xBA0)
            if value != 0:
                break
        if value == 1:
            self.SB_HalClearInterruptBit()
            self.SaSi_PalDmaUnMap(val)
            return 0
        else:
            return 0xF6000001

    def SBROM_AesCmacDriver(self, encmode, saltptr, saltptr2, dataptr, dataptr2, destptr, bufferlength):
        if encmode == 1:
            if self.read32(self.dxcc_base + self.DX_HOST_SEP_HOST_GPR4) & 2 != 0:
                keylen = 0x20
            else:
                keylen = 0x10
        else:
            keylen = 0x10
        self.SB_HalInit()
        outputlen = (keylen << 19) - 0x800000  # 0x0
        data = []
        data.append(0x0)  # 0
        data.append(0x8000041)  # 1
        data.append(0x0)  # 2
        data.append(0x0)  # 3
        data.append(outputlen | 0x1001C20)  # 4
        data.append(0x0)  # 5
        self.SaSi_SB_AddDescSequence(data)
        data[0] = 0
        data[1] = 0
        data[2] = 0
        data[3] = 0
        data[5] = 0
        if encmode == 0:
            data[0] = saltptr
            data[1] = 0x42
            data[5] = (saltptr >> 32) << 16
        data[4] = outputlen | ((encmode & 3) << 15) | (((encmode >> 2) & 3) << 20) | 0x4001C20  # 04009C20
        self.SaSi_SB_AddDescSequence(data)
        data[0] = dataptr
        data[1] = (4 * (bufferlength & 0xFFFFFF)) | 2  # 3E
        data[2] = 0
        data[3] = 0
        data[4] = 1
        data[5] = (dataptr2 >> 32) << 16
        self.SaSi_SB_AddDescSequence(data)
        if encmode != 2:
            data[0] = 0
            data[1] = 0
            data[2] = saltptr  # 120934
            data[3] = 0x42
            data[4] = 0x8001C26
            data[5] = (saltptr2 >> 32) << 16
            self.SaSi_SB_AddDescSequence(data)
        return self.SB_HalWaitDescCompletion(destptr) == 0
