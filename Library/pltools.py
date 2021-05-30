#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2021 MIT License
import os
import logging
from binascii import hexlify
from struct import pack, unpack
from Library.utils import LogBase, print_progress, logsetup
from Library.hwcrypto import crypto_setup, hwcrypto
from Library.kamakiri import Kamakiri
from Library.Port import Port


class PLTools(metaclass=LogBase):
    def __init__(self, mtk, loglevel=logging.INFO):
        self.__logger = logsetup(self, self.__logger, loglevel)
        self.mtk = mtk
        self.chipconfig = self.mtk.config.chipconfig
        self.config = self.mtk.config
        self.usbwrite = self.mtk.port.usbwrite
        self.usbread = self.mtk.port.usbread
        self.read32 = self.mtk.preloader.read32
        self.write32 = self.mtk.preloader.write32
        self.hwcode = mtk.config.hwcode

        # exploit types
        self.kama = Kamakiri(self.mtk, self.__logger.level)

        # crypto types
        setup=crypto_setup()
        setup.hwcode = self.mtk.config.hwcode
        setup.dxcc_base = self.mtk.config.chipconfig.dxcc_base
        setup.read32 = self.mtk.preloader.read32
        setup.write32 = self.mtk.preloader.write32
        setup.writemem = self.mtk.preloader.writemem
        setup.da_payload_addr = self.mtk.config.chipconfig.da_payload_addr
        setup.gcpu_base = self.mtk.config.chipconfig.gcpu_base
        setup.blacklist = self.mtk.config.chipconfig.blacklist
        setup.sej_base = self.mtk.config.chipconfig.sej_base
        setup.cqdma_base = self.mtk.config.chipconfig.cqdma_base
        setup.ap_dma_mem = self.mtk.config.chipconfig.ap_dma_mem
        self.hwcrypto=hwcrypto(setup,loglevel)

        if loglevel == logging.DEBUG:
            logfilename = os.path.join("logs", "log.txt")
            if os.path.exists(logfilename):
                os.remove(logfilename)
            fh = logging.FileHandler(logfilename)
            self.__logger.addHandler(fh)
            self.__logger.setLevel(logging.DEBUG)
        else:
            self.__logger.setLevel(logging.INFO)

    def runpayload(self, filename, ptype, offset=0, ack=0xA1A2A3A4, addr=None, dontack=False):
        try:
            with open(filename, "rb") as rf:
                rf.seek(offset)
                payload = rf.read()
                self.info(f"Loading payload from {filename}, {hex(len(payload))} bytes")
        except FileNotFoundError:
            self.info(f"Couldn't open {filename} for reading.")
            return False

        if addr is None:
            if ptype == "amonet":
                addr = self.chipconfig.da_payload_addr
            elif ptype == "kamakiri":
                addr = self.chipconfig.brom_payload_addr
            elif ptype == "hashimoto":
                addr = self.chipconfig.da_payload_addr
            elif ptype == "":
                if self.mtk.config.target_config["sla"] or self.mtk.config.target_config["daa"]:
                    addr = self.chipconfig.brom_payload_addr
                else:
                    addr = self.chipconfig.da_payload_addr

        if ptype == "amonet":
            self.info("Amonet Run")
            if self.payload(payload, addr, ptype):
                if dontack:
                    return True
                result = self.usbread(4)
                if result == pack(">I", ack):
                    self.info("Successfully sent payload: " + filename)
                    return True
                self.info("Error, payload answered instead: " + hexlify(result).decode('utf-8'))
                return False
            else:
                self.error("Error on sending payload: " + filename)
            return True
        elif ptype == "kamakiri":
            self.info("Kamakiri / DA Run")
            if self.kama.payload(payload, addr, True):
                if dontack:
                    return True
                result = self.usbread(4)
                if result == pack(">I", ack):
                    self.info("Successfully sent payload: " + filename)
                    return True
                self.info("Error, payload answered instead: " + hexlify(result).decode('utf-8'))
                return False
            else:
                self.error("Error on sending payload: " + filename)
        elif ptype == "hashimoto":
            self.info("Hashimoto Run")
            if self.payload(payload, addr, "cqdma"):
                if dontack:
                    return True
                result = self.usbread(4)
                if result == pack(">I", ack):
                    self.info("Successfully sent payload: " + filename)
                    return True
                self.info("Error, payload answered instead: " + hexlify(result).decode('utf-8'))
                return False
            else:
                self.error("Error on sending payload: " + filename)
        else:
            self.info("Kamakiri / DA Run")
            if self.kama.payload(payload, addr, False):
                if dontack:
                    return True
                result = self.usbread(4)
                if result == pack(">I", ack):
                    self.info("Successfully sent payload: " + filename)
                    return True
                self.info("Error, payload answered instead: " + hexlify(result).decode('utf-8'))
                return False
            else:
                self.error("Error on sending payload: " + filename)

    def crash(self, mode=0):
        self.info("Crashing da...")
        try:
            if mode == 1:
                self.mtk.preloader.send_da(0, 0x100, 0x100, b'\x00' * 0x100)
            elif mode == 2:
                self.mtk.preloader.read32(0, 0x100)
            elif mode == 0:
                payload = b'\x00\x01\x9F\xE5\x10\xFF\x2F\xE1' + b'\x00' * 0x110
                self.mtk.preloader.send_da(0x0, len(payload), 0x0, payload)
                self.mtk.preloader.jump_da(0x0)
        except:
            pass

    def crasher(self, mtk, enforcecrash):
        plt = PLTools(mtk, self.__logger.level)
        if enforcecrash or not (mtk.port.cdc.vid == 0xE8D and mtk.port.cdc.pid == 0x0003):
            self.info("We're not in bootrom, trying to crash da...")
            for crashmode in range(0, 3):
                try:
                    plt.crash(crashmode)
                except Exception as e:
                    self.__logger.debug(str(e))
                    pass
                portconfig = [[0xE8D, 0x0003, 1]]
                mtk.port = Port(mtk, portconfig, self.__logger.level)
                if mtk.preloader.init(maxtries=20):
                    break
        return mtk

    def run_dump_brom(self, filename, btype):
        pfilename = os.path.join("payloads", "generic_dump_payload.bin")
        if btype == "amonet":
            if self.dump_brom(filename, "gcpu"):
                self.info("Bootrom dumped as: " + filename)
                return True
            else:
                self.error("Error on sending payload: " + pfilename)
        elif btype == "hashimoto":
            if self.dump_brom(filename, "cqdma"):
                self.info("Bootrom dumped as: " + filename)
                return True
            else:
                self.error("Error on sending payload: " + pfilename)
        elif btype == "kamakiri" or btype is None:
            self.info("Kamakiri / DA Run")
            if self.runpayload(filename=pfilename, ptype="kamakiri", ack=0xC1C2C3C4, offset=0):
                if self.kama.dump_brom(filename):
                    self.info("Bootrom dumped as: " + filename)
                    return True
            else:
                self.error("Error on sending payload: " + filename)
        elif btype == "test":
            self.hwcrypto.disable_range_blacklist("cqdma",self.mtk.preloader.run_ext_cmd)
            data=self.hwcrypto.aes_hwcrypt(data=b"",encrypt=False,mode="fde",btype="dxcc")
            print(hexlify(data).decode('utf-8'))
            exit(0)
        else:
            self.error("Unknown dumpbrom ptype: " + btype)
            self.info("Available ptypes are: amonet, kamakiri, hashimoto")
        self.error("Error on dumping Bootrom.")
        return False

    def run_crypto(self, data, iv, btype="sej", encrypt=True):
        if data is None:
            data = bytearray()
        for i in range(32):
            data.append(self.config.meid[i % len(self.config.meid)])
        if btype == "":
            encrypted = self.hwcrypto.aes_hwcrypt(data=data, iv=iv, encrypt=encrypt, btype=btype)
            return encrypted
        return False

    def dump_brom(self, filename, btype):
        if btype == "gcpu" and self.chipconfig.gcpu_base is None:
            self.error("Chipconfig has no gcpu_base field for this cpu")
            return False
        elif btype == "cqdma" and self.chipconfig.cqdma_base is None or self.chipconfig.ap_dma_mem is None:
            self.error("Chipconfig has no cqdma_base and/or ap_dma_mem field for this cpu")
            return False
        if self.chipconfig.blacklist:
            self.hwcrypto.disable_range_blacklist(btype,self.mtk)
        self.info("Dump bootrom")
        print_progress(0, 100, prefix='Progress:', suffix='Complete', bar_length=50)
        old = 0
        with open(filename, 'wb') as wf:
            for addr in range(0x0, 0x20000, 16):
                prog = int(addr / 0x20000 * 100)
                if round(prog, 1) > old:
                    print_progress(prog, 100, prefix='Progress:', suffix='Complete, addr %08X' % addr,
                                   bar_length=50)
                    old = round(prog, 1)
                if btype == "gcpu":
                    wf.write(self.hwcrypto.gcpu.aes_read_cbc(addr))
                elif btype == "cqdma":
                    if not self.chipconfig.blacklist:
                        wf.write(self.hwcrypto.cqdma.mem_read(addr, 16, True))
                    else:
                        wf.write(self.hwcrypto.cqdma.mem_read(addr, 16, False))
        print_progress(100, 100, prefix='Progress:', suffix='Complete', bar_length=50)
        return True

    def payload(self, payload, daaddr, ptype):
        self.hwcrypto.disable_range_blacklist(ptype,self.mtk.preloader.run_ext_cmd)
        try:
            while len(payload) % 4 != 0:
                payload += b"\x00"

            words = []
            for x in range(len(payload) // 4):
                word = payload[x * 4:(x + 1) * 4]
                word = unpack("<I", word)[0]
                words.append(word)

            self.info("Sending payload")
            self.write32(self, words)

            self.info("Running payload ...")
            self.write32(self.mtk.config.chipconfig.blacklist[0][0] + 0x40, daaddr)
            return True
        except Exception as e:
            self.error("Failed to load payload file. Error: " + str(e))
            return False

