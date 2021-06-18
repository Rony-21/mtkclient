#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2021 MIT License
import os
import sys
import logging
from Library.utils import LogBase, logsetup
import time
from Library.usblib import usb_class
from binascii import hexlify
from struct import pack


class Port(metaclass=LogBase):
    class deviceclass:
        vid = 0
        pid = 0

        def __init__(self, vid, pid):
            self.vid = vid
            self.pid = pid

    def __init__(self, mtk, portconfig, loglevel=logging.INFO):
        self.__logger = logsetup(self, self.__logger, loglevel)
        self.config = mtk.config
        self.mtk = mtk
        self.cdc = usb_class(portconfig=portconfig, loglevel=loglevel, devclass=10)
        self.usbread = self.cdc.usbread
        self.usbwrite = self.cdc.usbwrite
        self.close = self.cdc.close
        self.rdword = self.cdc.rdword
        self.rword = self.cdc.rword
        self.rbyte = self.cdc.rbyte
        self.detectusbdevices = self.cdc.detectusbdevices
        self.usbreadwrite = self.cdc.usbreadwrite

        if loglevel == logging.DEBUG:
            logfilename = os.path.join("logs", "log.txt")
            fh = logging.FileHandler(logfilename)
            self.__logger.addHandler(fh)
            self.__logger.setLevel(logging.DEBUG)
        else:
            self.__logger.setLevel(logging.INFO)

    def posthandshake(self):
        startcmd = [b"\xa0", b"\x0a", b"\x50", b"\x05"]
        length = len(startcmd)
        tries = 100
        i = 0
        while i < length and tries > 0:
            if self.cdc.device.write(self.cdc.EP_OUT, startcmd[i]):
                time.sleep(0.01)
                v = self.cdc.device.read(self.cdc.EP_IN, 1, None)
                if v==b"R" and i==0: # We expect READY to be send
                    v = self.cdc.device.read(self.cdc.EP_IN, 4, None)
                    continue
                if v[0] == ~(startcmd[i][0]) & 0xFF:
                    i += 1
                else:
                    i = 0
                    self.cdc.setbreak()
                    self.cdc.setLineCoding(self.config.baudrate)
                    tries -= 1
        print()
        self.info("Device detected :)")
        return True

    def handshake(self, maxtries=None, loop=0):
        counter = 0
        startcmd = [b"\xa0", b"\x0a", b"\x50", b"\x05"]
        length = len(startcmd)

        while not self.cdc.connected:
            try:
                if maxtries is not None:
                    if counter == maxtries:
                        break
                counter += 1
                self.cdc.connected = self.cdc.connect()
                if self.cdc.connected:
                    # self.cdc.setLineCoding(19200)
                    # self.cdc.setcontrollinestate(RTS=True,DTR=True)
                    # self.cdc.setbreak()
                    tries = 100
                    i = 0
                    # self.cdc.setLineCoding(115200)
                    # self.cdc.setbreak()

                    while i < length and tries > 0:
                        if self.cdc.device.write(self.cdc.EP_OUT, startcmd[i]):
                            time.sleep(0.005)
                            try:
                                v = self.cdc.device.read(self.cdc.EP_IN, 64, None)
                                if len(v) == 1:
                                    if v[0] == ~(startcmd[i][0]) & 0xFF:
                                        i += 1
                                    else:
                                        i = 0
                                        self.cdc.setbreak()
                                        self.cdc.setLineCoding(self.config.baudrate)
                                        tries -= 1
                            except Exception as serr:
                                self.debug(str(serr))
                                i = 0
                                time.sleep(0.005)

                        """
                        if len(v) < 1:
                            self.debug("Timeout")
                            i = 0
                            time.sleep(0.005)
                        """
                    print()
                    self.info("Device detected :)")
                    return True
                else:
                    sys.stdout.write('.')
                    if loop >= 20:
                        sys.stdout.write('\n')
                        loop = 0
                    loop += 1
                    time.sleep(0.3)
                    sys.stdout.flush()
            except Exception as serr:
                if "access denied" in str(serr):
                    self.warning(str(serr))
                self.debug(str(serr))
                pass
        return False

    def mtk_cmd(self, value, bytestoread=0, nocmd=False):
        resp = b""
        dlen = len(value)
        wr = self.usbwrite(value)
        if wr:
            if nocmd:
                cmdrsp = self.usbread(bytestoread)
                return cmdrsp
            else:
                cmdrsp = self.usbread(dlen)
                if cmdrsp[0] is not value[0]:
                    self.error("Cmd error :" + hexlify(cmdrsp).decode('utf-8'))
                    return -1
                if bytestoread > 0:
                    resp = self.usbread(bytestoread)
                return resp
        else:
            self.warning("Couldn't send :" + hexlify(value).decode('utf-8'))
            return resp

    def echo(self, data):
        if isinstance(data, int):
            data = pack(">I", data)
        if isinstance(data, bytes):
            data = [data]
        for val in data:
            self.usbwrite(val)
            tmp = self.usbread(len(val))
            if val != tmp:
                return False
        return True
