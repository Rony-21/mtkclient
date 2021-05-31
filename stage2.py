#!/usr/bin/env python3
import os
import logging
import sys
import time
import argparse
from binascii import hexlify
from struct import pack, unpack
from Library.usblib import usb_class
from Library.utils import LogBase
from Library.utils import print_progress
from Library.hwcrypto import crypto_setup, hwcrypto
from config.brom_config import Mtk_Config


class Stage2(metaclass=LogBase):
    def init_emmc(self):
        self.cdc.usbwrite(pack(">I", 0xf00dd00d))
        self.cdc.usbwrite(pack(">I", 0x6000))
        time.sleep(5)
        if unpack("<I", self.cdc.usbread(4, 4))[0]==0xD1D1D1D1:
            return True
        self.emmc_inited = True
        return False

    def read32(self, addr, dwords=1):
        result = []
        for pos in range(dwords):
            self.cdc.usbwrite(pack(">I", 0xf00dd00d))
            self.cdc.usbwrite(pack(">I", 0x4002))
            self.cdc.usbwrite(pack(">I", addr + (pos * 4)))
            self.cdc.usbwrite(pack(">I", 4))
            result.append(unpack("<I", self.cdc.usbread(4, 4))[0])
        if len(result) == 1:
            return result[0]
        return result

    def cmd_C8(self, val) -> bool:
        'Clear cache func'
        self.cdc.usbwrite(pack(">I", 0xf00dd00d))
        self.cdc.usbwrite(pack(">I", 0x5000))
        ack = self.cdc.usbread(4)
        if ack == b"\xD0\xD0\xD0\xD0":
            return True
        return False

    def write32(self, addr, dwords) -> bool:
        if isinstance(dwords, int):
            dwords = [dwords]
        for pos in range(0, len(dwords)):
            self.cdc.usbwrite(pack(">I", 0xf00dd00d))
            self.cdc.usbwrite(pack(">I", 0x4000))
            self.cdc.usbwrite(pack(">I", addr + (pos * 4)))
            self.cdc.usbwrite(pack(">I", 4))
            self.cdc.usbwrite(pack("<I", dwords[pos]))
            ack = self.cdc.usbread(4)
            if ack == b"\xD0\xD0\xD0\xD0":
                continue
            else:
                return False
        return True

    def __init__(self, args, loglevel=logging.INFO):
        self.__logger = self.__logger
        self.args = args
        self.info = self.__logger.info
        self.error = self.__logger.error
        self.warning = self.__logger.warning
        self.emmc_inited = False
        # Setup HW Crypto chip variables
        setup = crypto_setup()
        with open(os.path.join("logs", "hwcode"), "rb") as rf:
            hwcode = int(rf.read(), 16)
            self.config = Mtk_Config(loglevel)
            self.config.init_hwcode(hwcode)
            setup.blacklist = self.config.chipconfig.blacklist
            setup.gcpu_base = self.config.chipconfig.gcpu_base
            setup.dxcc_base = self.config.chipconfig.dxcc_base
            setup.da_payload_addr = self.config.chipconfig.da_payload_addr
            setup.sej_base = self.config.chipconfig.sej_base
            setup.read32 = self.read32
            setup.write32 = self.write32
            setup.writemem = self.memwrite
        self.hwcrypto = hwcrypto(setup, loglevel)

        if loglevel == logging.DEBUG:
            logfilename = os.path.join("logs", "log.txt")
            if os.path.exists(logfilename):
                os.remove(logfilename)
            fh = logging.FileHandler(logfilename)
            self.__logger.addHandler(fh)
            self.__logger.setLevel(logging.DEBUG)
        else:
            self.__logger.setLevel(logging.INFO)

        portconfig = [[0x0E8D, 0x0003, -1], [0x0E8D, 0x2000, -1]]
        self.cdc = usb_class(portconfig=portconfig, loglevel=loglevel, devclass=10)

    def connect(self):
        self.cdc.connected = self.cdc.connect()
        return self.cdc.connected

    def close(self):
        if self.cdc.connected:
            self.cdc.close()

    def readflash(self, type: int, start, length, display=False, filename: str = None):
        if not self.emmc_inited:
            self.init_emmc()
        wf = None
        buffer = bytearray()
        if filename is not None:
            wf = open(filename, "wb")
        sectors = (length // 0x200)
        sectors += (1 if length % 0x200 else 0)
        startsector = (start // 0x200)
        # emmc_switch(1)
        self.cdc.usbwrite(pack(">I", 0xf00dd00d))
        self.cdc.usbwrite(pack(">I", 0x1002))
        self.cdc.usbwrite(pack(">I", type))

        if display:
            print_progress(0, 100, prefix='Progress:', suffix='Complete', bar_length=50)

        # kick-wdt
        # self.cdc.usbwrite(pack(">I", 0xf00dd00d))
        # self.cdc.usbwrite(pack(">I", 0x3001))

        bytestoread = length
        bytesread = 0
        old = 0
        # emmc_read(0)
        for sector in range(startsector, sectors):
            self.cdc.usbwrite(pack(">I", 0xf00dd00d))
            self.cdc.usbwrite(pack(">I", 0x1000))
            self.cdc.usbwrite(pack(">I", sector))
            tmp = self.cdc.usbread(0x200, 0x200)
            if len(tmp) != 0x200:
                self.error("Error on getting data")
                return
            if display:
                prog = sector / sectors * 100
                if round(prog, 1) > old:
                    print_progress(prog, 100, prefix='Progress:',
                                   suffix='Complete, Sector:' + hex((sectors * 0x200) - bytestoread),
                                   bar_length=50)
                    old = round(prog, 1)
            bytesread += len(tmp)
            size = min(bytestoread, len(tmp))
            if wf is not None:
                wf.write(tmp[:size])
            else:
                buffer.extend(tmp)
            bytestoread -= size
        if display:
            print_progress(100, 100, prefix='Complete: ', suffix=filename, bar_length=50)
        if wf is not None:
            wf.close()
        else:
            return buffer[start % 0x200:(start % 0x200) + length]

    def preloader(self, start, length, filename):
        sectors = 0
        if start != 0:
            start = (start // 0x200)
        if length != 0:
            sectors = (length // 0x200) + (1 if length % 0x200 else 0)
        self.info("Reading preloader...")
        if self.cdc.connected:
            if sectors == 0:
                buffer = self.readflash(type=1, start=0, length=0x4000, display=False)
                if len(buffer) != 0x4000:
                    print("Error on reading boot1 area.")
                    return
                if buffer[:9] == b'EMMC_BOOT':
                    startbrlyt = unpack("<I", buffer[0x10:0x14])[0]
                    if buffer[startbrlyt:startbrlyt + 5] == b"BRLYT":
                        start = unpack("<I", buffer[startbrlyt + 0xC:startbrlyt + 0xC + 4])[0]
                        st = buffer[start:start + 4]
                        if st == b"MMM\x01":
                            length = unpack("<I", buffer[start + 0x20:start + 0x24])[0]
                            data = self.readflash(type=1, start=0, length=start + length, display=True)
                            if len(data) != start + length:
                                print("Warning, please rerun command, length doesn't match.")
                            idx = data.find(b"MTK_BLOADER_INFO")
                            if idx != -1:
                                filename = data[idx + 0x1B:idx + 0x3D].rstrip(b"\x00").decode('utf-8')
                            with open(os.path.join("logs", filename), "wb") as wf:
                                wf.write(data[start:start + length])
                                print("Done writing to " + os.path.join("logs", filename))
                            with open(os.path.join("logs", "hdr_" + filename), "wb") as wf:
                                wf.write(data[:start])
                                print("Done writing to " + os.path.join("logs", "hdr_" + filename))

                            return
                else:
                    length = 0x40000
                    self.readflash(type=1, start=0, length=length, display=True, filename=filename)
                    print("Done")
                print("Error on getting preloader info, aborting.")
            else:
                self.readflash(type=1, start=start, length=length, display=True, filename=filename)
            print("Done")

    def memread(self, start, length, filename=None):
        bytestoread = length
        addr = start
        data = b""
        pos = 0
        if filename is not None:
            wf = open(filename, "wb")
        while bytestoread > 0:
            size = min(bytestoread, 0x200)
            self.cdc.usbwrite(pack(">I", 0xf00dd00d))
            self.cdc.usbwrite(pack(">I", 0x4002))
            self.cdc.usbwrite(pack(">I", addr + pos))
            self.cdc.usbwrite(pack(">I", size))
            if filename is None:
                data += self.cdc.usbread(size, size)
            else:
                wf.write(self.cdc.usbread(size, size))
            bytestoread -= size
            pos += size
        self.info(f"{hex(start)}: " + hexlify(data).decode('utf-8'))
        if filename is not None:
            wf.close()
        return data

    def memwrite(self, start, data, filename=None):
        if filename is not None:
            rf = open(filename, "rb")
            bytestowrite = os.stat(filename).st_size
        else:
            if isinstance(data, str):
                data = bytes.fromhex(data)
            elif isinstance(data, int):
                data = pack("<I", data)
            bytestowrite = len(data)
        addr = start
        pos = 0
        while bytestowrite > 0:
            size = min(bytestowrite, 0x200)
            self.cdc.usbwrite(pack(">I", 0xf00dd00d))
            self.cdc.usbwrite(pack(">I", 0x4000))
            self.cdc.usbwrite(pack(">I", addr + pos))
            self.cdc.usbwrite(pack(">I", size))
            if filename is None:
                wdata = data[pos:pos + size]
            else:
                wdata = rf.read(size)
            bytestowrite -= size
            pos += size
            while len(wdata) % 4 != 0:
                wdata += b"\x00"
            self.cdc.usbwrite(wdata)

        if filename is not None:
            rf.close()
        ack = self.cdc.usbread(4)
        if ack == b"\xD0\xD0\xD0\xD0":
            return True
        else:
            return False

    def rpmb(self, start, length, filename, reverse=False):
        if start == 0:
            start = 0
        else:
            start = (start // 0x100)
        if length == 0:
            sectors = 4 * 1024 * 1024 // 0x100
        else:
            sectors = (length // 0x100) + (1 if length % 0x100 else 0)
        self.info("Reading rpmb...")

        self.cdc.usbwrite(pack(">I", 0xf00dd00d))
        self.cdc.usbwrite(pack(">I", 0x1002))
        self.cdc.usbwrite(pack(">I", 0x1))

        # kick-wdt
        # self.cdc.usbwrite(pack(">I", 0xf00dd00d))
        # self.cdc.usbwrite(pack(">I", 0x3001))

        print_progress(0, 100, prefix='Progress:', suffix='Complete', bar_length=50)
        bytesread = 0
        old = 0
        bytestoread = sectors * 0x100
        with open(filename, "wb") as wf:
            for sector in range(start, sectors):
                self.cdc.usbwrite(pack(">I", 0xf00dd00d))
                self.cdc.usbwrite(pack(">I", 0x2000))
                self.cdc.usbwrite(pack(">H", sector))
                tmp = self.cdc.usbread(0x100, 0x100)
                if reverse:
                    tmp = tmp[::-1]
                if len(tmp) != 0x100:
                    self.error("Error on getting data")
                    return
                prog = sector / sectors * 100
                if round(prog, 1) > old:
                    print_progress(prog, 100, prefix='Progress:',
                                   suffix='Complete, Sector:' + hex((sectors * 0x200) - bytestoread),
                                   bar_length=50)
                    old = round(prog, 1)
                bytesread += 0x100
                size = min(bytestoread, len(tmp))
                wf.write(tmp[:size])
                bytestoread -= size
            print_progress(100, 100, prefix='Complete: ', suffix=filename, bar_length=50)
        print("Done")

    def hwkey(self,type,data=b"",otp=None,mode="dxcc"):
        data = self.hwcrypto.aes_hwcrypt(data=data, encrypt=False, mode=type, btype=mode, otp=otp)
        return data

    def reboot(self):
        self.cdc.usbwrite(pack(">I", 0xf00dd00d))
        self.cdc.usbwrite(pack(">I", 0x3000))


def getint(valuestr):
    if valuestr == '':
        return None
    try:
        return int(valuestr)
    except Exception as err:
        err = err
        try:
            return int(valuestr, 16)
        except Exception as err:
            err = err
            pass
    return 0


cmds = {
    "rpmb": 'Dump rpmb',
    "preloader": 'Dump preloader',
    "reboot": 'Reboot phone',
    "memread": "Read memory [Example: memread --start 0 --length 0x10]",
    "memwrite": "Write memory [Example: memwrite --start 0x200000 --data 11223344",
}

info = "MTK Stage2 client (c) B.Kerler 2021"


def showcommands():
    print(info)
    print("-----------------------------------\n")
    print("Available commands are:\n")
    for cmd in cmds:
        print("%20s" % (cmd) + ":\t" + cmds[cmd])
    print()


def main():
    parser = argparse.ArgumentParser(description=info)
    parser.add_argument("cmd", help="Valid commands are: rpmb, preloader, memread, memwrite")
    parser.add_argument('--reverse', dest='reverse', action="store_true",
                        help='Reverse byte order (example: rpmb command)')
    parser.add_argument('--length', dest='length', type=str,
                        help='Max length to dump')
    parser.add_argument('--start', dest='start', type=str,
                        help='Start offset to dump')
    parser.add_argument('--data', dest='data', type=str,
                        help='Data to write')
    parser.add_argument('--filename', dest='filename', type=str,
                        help='Read from / save to filename')
    args = parser.parse_args()
    cmd = args.cmd
    if cmd not in cmds:
        showcommands()
        exit(0)

    start = getint(args.start)
    length = getint(args.length)
    if not os.path.exists("logs"):
        os.mkdir("logs")
    st2 = Stage2(args)
    if st2.connect():
        if cmd == "rpmb":
            if args.filename is None:
                filename = os.path.join("logs", "rpmb")
            else:
                filename = args.filename
            st2.rpmb(start, length, filename, args.reverse)
        elif cmd == "preloader":
            if args.filename is None:
                filename = os.path.join("logs", "preloader")
            else:
                filename = args.filename
            st2.preloader(start, length, filename=filename)
        elif cmd == "memread":
            if args.start is None:
                print("Option --start is needed")
                exit(0)
            if args.length is None:
                print("Option --length is needed")
                exit(0)
            st2.memread(start, length, args.filename)
        elif cmd == "memwrite":
            if args.start is None:
                print("Option --start is needed")
                exit(0)
            if args.data is None:
                print("Option --data is needed")
                exit(0)
            if st2.memwrite(start, args.data, args.filename):
                print(f"Successfully wrote data to {hex(start)}.")
            else:
                print(f"Failed to write data to {hex(start)}.")
        elif cmd == "reboot":
            st2.reboot()
    st2.close()


if __name__ == "__main__":
    main()
