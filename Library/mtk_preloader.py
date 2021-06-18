#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2021 MIT License
import os
import logging
from Library.utils import LogBase, logsetup
from enum import Enum
from struct import unpack, pack
from binascii import hexlify
from Library.error import ErrorHandler
from Library.utils import getint


class Preloader(metaclass=LogBase):
    class Rsp(Enum):
        NONE = b''
        CONF = b'\x69'
        STOP = b'\x96'
        ACK = b'\x5A'
        NACK = b'\xA5'

    class Cap(Enum):
        PL_CAP0_XFLASH_SUPPORT = (0x1 << 0)
        PL_CAP0_MEID_SUPPORT = (0x1 << 1)
        PL_CAP0_SOCID_SUPPORT = (0x1 << 2)

    class Cmd(Enum):
        # if CFG_PRELOADER_AS_DA
        SEND_PARTITION_DATA = b"\x70"
        JUMP_TO_PARTITION = b"\x71"

        CHECK_USB_CMD = b"\x72"
        STAY_STILL = b"\x80"
        CMD_88 = b"\x88"
        CMD_READ16_A2 = b"\xA2"

        I2C_INIT = b"\xB0"
        I2C_DEINIT = b"\xB1"
        I2C_WRITE8 = b"\xB2"
        I2C_READ8 = b"\xB3"
        I2C_SET_SPEED = b"\xB4"
        I2C_INIT_EX = b"\xB6"
        I2C_DEINIT_EX = b"\xB7"  # JUMP_MAUI
        I2C_WRITE8_EX = b"\xB8"  # READY
        """
        / Boot-loader resposne from BLDR_CMD_READY (0xB8)
        STATUS_READY				0x00		// secure RO is found and ready to serve
        STATUS_SECURE_RO_NOT_FOUND  0x01		// secure RO is not found: first download? => dead end...
        STATUS_SUSBDL_NOT_SUPPORTED	0x02		// BL didn't enable Secure USB DL
        """
        I2C_READ8_EX = b"\xB9"
        I2C_SET_SPEED_EX = b"\xBA"
        GET_MAUI_FW_VER = b"\xBF"

        OLD_SLA_SEND_AUTH = b"\xC1"
        OLD_SLA_GET_RN = b"\xC2"
        OLD_SLA_VERIFY_RN = b"\xC3"
        PWR_INIT = b"\xC4"
        PWR_DEINIT = b"\xC5"
        PWR_READ16 = b"\xC6"
        PWR_WRITE16 = b"\xC7"
        CMD_C8 = b"\xC8"  # RE

        READ16 = b"\xD0"
        READ32 = b"\xD1"
        WRITE16 = b"\xD2"
        WRITE16_NO_ECHO = b"\xD3"
        WRITE32 = b"\xD4"
        JUMP_DA = b"\xD5"
        JUMP_BL = b"\xD6"
        SEND_DA = b"\xD7"
        GET_TARGET_CONFIG = b"\xD8"
        SEND_ENV_PREPARE = b"\xD9"
        CMD_DA = b"\xDA"
        UART1_LOG_EN = b"\xDB"
        UART1_SET_BAUDRATE = b"\xDC",  # RE
        BROM_DEBUGLOG = b"\xDD",  # RE
        JUMP_DA64 = b"\xDE",  # RE
        GET_BROM_LOG_NEW = b"\xDF",  # RE

        SEND_CERT = b"\xE0",
        GET_ME_ID = b"\xE1"
        SEND_AUTH = b"\xE2"
        SLA = b"\xE3"
        CMD_E4 = b"\xE4"
        CMD_E5 = b"\xE5"
        CMD_E6 = b"\xE6"
        GET_SOC_ID = b"\xE7"

        ZEROIZATION = b"\xF0"
        GET_PL_CAP = b"\xFB"
        GET_HW_SW_VER = b"\xFC"
        GET_HW_CODE = b"\xFD"
        GET_BL_VER = b"\xFE"
        GET_VERSION = b"\xFF"

    def __init__(self, mtk, loglevel=logging.INFO):
        self.mtk = mtk
        self.__logger = logsetup(self, self.__logger, loglevel)
        self.eh = ErrorHandler()
        self.gcpu = None
        self.config = mtk.config
        self.display = True
        self.rbyte = self.mtk.port.rbyte
        self.rword = self.mtk.port.rword
        self.rdword = self.mtk.port.rdword
        self.usbread = self.mtk.port.usbread
        self.usbwrite = self.mtk.port.usbwrite
        self.echo = self.mtk.port.echo
        self.sendcmd = self.mtk.port.mtk_cmd

    def init(self, args, readsocid=False, maxtries=None):
        self.info("Status: Waiting for PreLoader VCOM, please connect mobile")
        if not self.mtk.port.handshake(maxtries=maxtries):
            self.error("No MTK PreLoader detected.")
            return False

        if not self.echo(self.Cmd.GET_HW_CODE.value):  # 0xFD
            if not self.echo(self.Cmd.GET_HW_CODE.value):
                self.error("Sync error. Please power off the device and retry.")
            return False
        else:
            self.config.hwcode = self.rword()
            self.config.hwver = self.rword()
            self.config.init_hwcode(self.config.hwcode)
        da_address = args["--da_addr"]
        if da_address is not None:
            self.info("O:DA offset:\t\t\t" + da_address)
            self.config.chipconfig.da_payload_addr = getint(da_address)

        brom_address = args["--brom_addr"]
        if brom_address is not None:
            self.info("O:Payload offset:\t\t" + brom_address)
            self.config.chipconfig.brom_payload_addr = getint(brom_address)

        watchdog_address = args["--wdt"]
        if watchdog_address is not None:
            self.info("O:Watchdog addr:\t\t" + watchdog_address)
            self.config.chipconfig.watchdog = getint(watchdog_address)

        uart_address = args["--uartaddr"]
        if uart_address is not None:
            self.info("O:Uart addr:\t\t" + uart_address)
            self.config.chipconfig.uart = getint(uart_address)

        var1 = args["--var1"]
        if var1 is not None:
            self.info("O:Var1:\t\t" + var1)
            self.config.chipconfig.var1 = getint(var1)

        cpu = self.config.chipconfig.name
        if self.display:
            self.info("\tCPU:\t\t\t" + cpu + "(" + self.config.chipconfig.description + ")")
            self.config.cpu = cpu.replace("/", "_")
            self.info("\tHW version:\t\t" + hex(self.config.hwver))
            self.info("\tWDT:\t\t\t" + hex(self.config.chipconfig.watchdog))
            self.info("\tUart:\t\t\t" + hex(self.config.chipconfig.uart))
            self.info("\tBrom payload addr:\t" + hex(self.config.chipconfig.brom_payload_addr))
            self.info("\tDA payload addr:\t" + hex(self.config.chipconfig.da_payload_addr))
            if self.config.chipconfig.cqdma_base is not None:
                self.info("\tCQ_DMA addr:\t\t" + hex(self.config.chipconfig.cqdma_base))
            self.info("\tVar1:\t\t\t" + hex(self.config.chipconfig.var1))

        res = self.get_hw_sw_ver()
        self.config.hwsubcode = 0
        self.config.hwver = 0
        self.config.swver = 0
        if res != -1:
            self.config.hwsubcode = res[0]
            self.config.hwver = res[1]
            self.config.swver = res[2]
        if self.display:
            self.info("\tHW subcode:\t\t" + hex(self.config.hwsubcode))
            self.info("\tHW Ver:\t\t\t" + hex(self.config.hwver))
            self.info("\tSW Ver:\t\t\t" + hex(self.config.swver))

        if not args["--skipwdt"]:
            if self.display:
                self.info("Disabling Watchdog...")
            self.setreg_disablewatchdogtimer(self.config.hwcode)  # D4
        if self.display:
            self.info("HW code:\t\t\t" + hex(self.config.hwcode))
            with open(os.path.join("logs", "hwcode"), "w") as wf:
                wf.write(hex(self.config.hwcode))
        self.config.target_config = self.get_target_config(self.display)
        blver=self.get_blver()
        meid = self.get_meid()
        if len(meid) >= 16:
            with open(os.path.join("logs", "meid"), "wb") as wf:
                wf.write(hexlify(meid))
        if self.display:
            if meid != b"":
                self.info("ME_ID:\t\t\t" + hexlify(meid).decode('utf-8').upper())
        if readsocid or self.config.chipconfig.has_socid:
            socid = self.get_socid()
            if len(socid) >= 16:
                with open(os.path.join("logs", "socid"), "wb") as wf:
                    wf.write(hexlify(socid))
            if self.display:
                if socid != b"":
                    self.info("SOC_ID:\t\t\t" + hexlify(socid).decode('utf-8').upper())

        return True

    def read32(self, addr, dwords=1) -> list:
        result = []
        if self.echo(self.Cmd.READ32.value):
            if self.echo(pack(">I", addr)):
                ack = self.echo(pack(">I", dwords))
                status = self.rword()
                if ack and status <= 0xFF:
                    result = self.rdword(dwords)
                    status2 = unpack(">H", self.usbread(2))[0]
                    if status2 <= 0xFF:
                        return result
                else:
                    self.error(self.eh.status(status))
        return result

    def write32(self, addr, dwords) -> bool:
        if isinstance(dwords, int):
            dwords = [dwords]
        if self.echo(self.Cmd.WRITE32.value):
            if self.echo(pack(">I", addr)):
                ack = self.echo(pack(">I", len(dwords)))
                status = self.rword()
                if status > 0xFF:
                    self.error(f"Error on da_write32, addr {hex(addr)}, {self.eh.status(status)}")
                    return False
                if ack and status <= 3:
                    for dword in dwords:
                        if not self.echo(pack(">I", dword)):
                            break
                    status2 = self.rword()
                    if status2 <= 0xFF:
                        return True
                    else:
                        self.error(f"Error on da_write32, addr {hex(addr)}, {self.eh.status(status2)}")
            else:
                self.error(f"Error on da_write32, addr {hex(addr)}, write address")
        else:
            self.error(f"Error on da_write32, addr {hex(addr)}, send cmd")
        return False

    def writemem(self, addr, data):
        for i in range(0, len(data), 4):
            value = data[i:i + 4]
            while len(value) < 4:
                value += b"\x00"
            self.write32(addr + i, unpack("<I", value))

    def run_ext_cmd(self, cmd=b"\xB1"):
        self.usbwrite(self.Cmd.CMD_C8.value)
        assert self.usbread(1) == self.Cmd.CMD_C8.value
        cmd = bytes([cmd])
        self.usbwrite(cmd)
        assert self.usbread(1) == cmd
        self.usbread(1)
        self.usbread(2)

    def jump_to_partition(self, partitionname):
        if isinstance(partitionname,str):
            partitionname=bytes(partitionname,'utf-8')[:64]
        partitionname=partitionname+(64-len(partitionname))*b'\x00'
        if self.echo(self.Cmd.JUMP_TO_PARTITION.value):
            self.usbwrite(partitionname)
            status2 = self.rword()
            if status2 <= 0xFF:
                return True

    def calc_xflash_checksum(self, data):
        checksum=0
        pos=0
        for i in range(0,len(data)//4):
            checksum+=unpack("<I", data[i * 4:(i * 4) + 4])[0]
            pos+=4
        if len(data)%4!=0:
            for i in range(4-(len(data)%4)):
                checksum+=data[pos]
                pos+=1
        return checksum&0xFFFFFFFF

    def send_partition_data(self, partitionname, data):
        checksum = self.calc_xflash_checksum(data)
        if isinstance(partitionname,str):
            partitionname=bytes(partitionname,'utf-8')[:64]
        partitionname=partitionname+(64-len(partitionname))*b'\x00'
        if self.echo(self.Cmd.SEND_PARTITION_DATA.value):
            self.usbwrite(partitionname)
            self.usbwrite(pack(">I",len(data)))
            status = self.rword()
            if status <= 0xFF:
                length = len(data)
                pos=0
                while length > 0:
                    dsize = min(length, 0x200)
                    if not self.usbwrite(data[pos:pos + dsize]):
                        break
                    pos += dsize
                    length -= dsize
                #self.usbwrite(data)
                self.usbwrite(pack(">I",checksum))



    def setreg_disablewatchdogtimer(self, hwcode):
        """
        SetReg_DisableWatchDogTimer; BRom_WriteCmd32(): Reg 0x10007000[1]={ Value 0x22000000 }.
        """
        addr, value = self.config.get_watchdog_addr()
        res = self.write32(addr, [value])
        if not res:
            self.error("Received wrong SetReg_DisableWatchDogTimer response")
            return False
        if hwcode == 0x6592:
            res = self.write32(0x10000500, [0x22000000])
            if res:
                return True
        elif hwcode in [0x6575, 0x6577]:
            res = self.write32(0x2200, [0xC0000000])
            if res:
                return True
        else:
            return True
        return False

    def get_blver(self):
        if self.usbwrite(self.Cmd.GET_BL_VER.value):
            res = self.usbread(1)
            if res == self.Cmd.GET_BL_VER.value:
                # We are in boot rom ...
                self.info("BROM mode detected.")
                self.mtk.config.blver = -2
                return -2
            else:
                self.mtk.config.blver=unpack("B", res)[0]
                return self.mtk.config.blver
        return -1

    def get_target_config(self, display=True):
        if self.echo(self.Cmd.GET_TARGET_CONFIG.value):
            target_config, status = unpack(">IH", self.rbyte(6))
            sbc = True if (target_config & 0x1) else False
            sla = True if (target_config & 0x2) else False
            daa = True if (target_config & 0x4) else False
            swjtag = True if (target_config & 0x6) else False
            epp = True if (target_config & 0x8) else False
            cert = True if (target_config & 0x10) else False
            memread = True if (target_config & 0x20) else False
            memwrite = True if (target_config & 0x40) else False
            cmd_c8 = True if (target_config & 0x80) else False
            if display:
                self.info(f"Target config:\t\t{hex(target_config)}")
                self.info(f"\tSBC enabled:\t\t{sbc}")
                self.info(f"\tSLA enabled:\t\t{sla}")
                self.info(f"\tDAA enabled:\t\t{daa}")
                self.info(f"\tSWJTAG enabled:\t\t{swjtag}")
                self.info(f"\tEPP_PARAM at 0x600 after EMMC_BOOT/SDMMC_BOOT:\t{epp}")
                self.info(f"\tRoot cert required:\t{cert}")
                self.info(f"\tMem read auth:\t\t{memread}")
                self.info(f"\tMem write auth:\t\t{memwrite}")
                self.info(f"\tCmd 0xC8 blocked:\t{cmd_c8}")

            if status > 0xff:
                raise Exception("Get Target Config Error")
            return {"sbc": sbc, "sla": sla, "daa": daa, "epp": epp, "cert": cert,
                    "memread": memread, "memwrite": memwrite, "cmdC8": cmd_c8}
        else:
            self.warning("CMD Get_Target_Config not supported.")
            return {"sbc": False, "sla": False, "daa": False, "epp": False, "cert": False,
                    "memread": False, "memwrite": False, "cmdC8": False}

    def jump_da(self, addr):
        self.info(f"Jumping to {hex(addr)}")
        if self.echo(self.Cmd.JUMP_DA.value):
            self.usbwrite(pack(">I", addr))
            data = b""
            try:
                resaddr = self.rdword()
            except Exception as e:
                self.error(f"Jump_DA Resp2 {str(e)} ," + hexlify(data).decode('utf-8'))
                return False
            if resaddr == addr:
                try:
                    status = self.rword()
                except Exception as e:
                    self.error(f"Jump_DA Resp2 {str(e)} ," + hexlify(data).decode('utf-8'))
                    return False
                if status == 0:
                    return True
                else:
                    self.error(f"Jump_DA status error:{self.eh.status(status)}")
        return False

    def jump_da64(self, addr: int):
        if self.echo(self.Cmd.JUMP_DA64.value):
            self.usbwrite(pack(">I", addr))
            try:
                resaddr = self.rdword()
            except Exception as e:
                self.error(f"Jump_DA Resp2 {str(e)} , addr {hex(addr)}")
                return False
            if resaddr == addr:
                self.echo(b"\x01")  # for 64Bit, 0 for 32Bit
                try:
                    status = self.rword()
                except Exception as e:
                    self.error(f"Jump_DA Resp2 {str(e)} , addr {hex(addr)}")
                    return False
                if status == 0:
                    return True
                else:
                    self.error(f"Jump_DA64 status error:{self.eh.status(status)}")
        return False

    def uart1_log_enable(self):
        if self.echo(self.Cmd.UART1_LOG_EN):
            status = self.rword()
            if status == 0:
                return True
            else:
                self.error(f"Uart1 log enable error:{self.eh.status(status)}")
        return False

    def uart1_set_baud(self, baudrate):
        if self.echo(self.Cmd.UART1_SET_BAUDRATE):
            self.usbwrite(baudrate)
            status = self.rword()
            if status == 0:
                return True
            else:
                self.error(f"Uart1 set baudrate error:{self.eh.status(status)}")
        return False

    def send_root_cert(self, cert):
        gen_chksum, data = self.prepare_data(cert)
        if self.echo(self.Cmd.SEND_CERT):
            self.usbwrite(len(data))
            status = self.rword()
            if 0x0 <= status <= 0xFF:
                if not self.upload_data(cert, gen_chksum):
                    self.error("Error on uploading certificate.")
                    return False
                return True
            self.error(f"Send cert error:{self.eh.status(status)}")
        return False

    def send_auth(self, auth):
        gen_chksum, data = self.prepare_data(auth)
        if self.echo(self.Cmd.SEND_AUTH):
            self.usbwrite(len(data))
            status = self.rword()
            if 0x0 <= status <= 0xFF:
                if not self.upload_data(data, gen_chksum):
                    self.error("Error on uploading auth.")
                    return False
                return True
            self.error(f"Send auth error:{self.eh.status(status)}")
        return False

    def get_brom_log_new(self):
        if self.echo(self.Cmd.GET_BROM_LOG_NEW):
            length = self.rdword()
            logdata = self.rbyte(length)
            status = self.rword()
            if status == 0:
                return logdata
            else:
                self.error(f"Brom log status error:{self.eh.status(status)}")
        return b""

    def get_hwcode(self):
        res = self.sendcmd(self.Cmd.GET_HW_CODE.value, 4)  # 0xFD
        return unpack(">HH", res)

    def get_plcap(self):
        res = self.sendcmd(self.Cmd.GET_PL_CAP.value, 8)  # 0xFB
        self.mtk.config.plcap = unpack(">II", res)
        return self.mtk.config.plcap

    def get_hw_sw_ver(self):
        res = self.sendcmd(self.Cmd.GET_HW_SW_VER.value, 8)  # 0xFC
        return unpack(">HHHH", res)

    def get_meid(self):
        if self.usbwrite(self.Cmd.GET_BL_VER.value):
            res = self.usbread(1)
            if res == self.Cmd.GET_BL_VER.value:
                self.usbwrite(self.Cmd.GET_ME_ID.value)  # 0xE1
                if self.usbread(1) == self.Cmd.GET_ME_ID.value:
                    length = unpack(">I", self.usbread(4))[0]
                    self.mtk.config.meid = self.usbread(length)
                    status = unpack("<H", self.usbread(2))[0]
                    if status == 0:
                        return self.mtk.config.meid
                    else:
                        self.error("Error on get_meid: " + self.eh.status(status))
        return b""

    def get_socid(self):
        if self.usbwrite(self.Cmd.GET_BL_VER.value):
            res = self.usbread(1)
            if res == self.Cmd.GET_BL_VER.value:
                self.usbwrite(self.Cmd.GET_SOC_ID.value)  # 0xE7
                if self.usbread(1) == self.Cmd.GET_SOC_ID.value:
                    length = unpack(">I", self.usbread(4))[0]
                    self.mtk.config.socid = self.usbread(length)
                    status = unpack("<H", self.usbread(2))[0]
                    if status == 0:
                        return self.mtk.config.socid
                    else:
                        self.error("Error on get_socid: " + self.eh.status(status))
        return b""

    def prepare_data(self, data, sigdata=None, maxsize=0):
        gen_chksum = 0
        data = (data[:maxsize] + sigdata)
        if len(data + sigdata) % 2 != 0:
            data += b"\x00"
        for i in range(0, len(data), 2):
            gen_chksum ^= unpack("<H", data[i:i + 2])[0]
        return gen_chksum, data

    def upload_data(self, data, gen_chksum):
        bytestowrite=len(data)
        pos=0
        while bytestowrite>0:
            size=min(bytestowrite,64)
            self.usbwrite(data[pos:pos + size])
            bytestowrite-=size
            pos+=size
        #self.usbwrite(b"")
        try:
            checksum, status = self.rword(2)
            if gen_chksum != checksum and checksum != 0:
                self.error("Checksum of upload doesn't match !")
                return False
            if 0 <= status <= 0xFF:
                return True
        except Exception as e:
            self.error(f"upload_data resp error : " + str(e))
            return False
        return True

    def send_da(self, address, size, sig_len, dadata):
        gen_chksum, data = self.prepare_data(dadata[:-sig_len], dadata[-sig_len:], size)
        if not self.echo(self.Cmd.SEND_DA.value):  # 0xD7
            self.error(f"Error on DA_Send cmd")
            return False
        if not self.echo(address):
            self.error(f"Error on DA_Send address")
            return False
        if not self.echo(len(data)):
            self.error(f"Error on DA_Send size")
            return False
        if not self.echo(sig_len):
            self.error(f"Error on DA_Send sig_len")
            return False

        status = self.rword()
        if 0 <= status <= 0xFF:
            if not self.upload_data(data, gen_chksum):
                self.error("Error on uploading da data")
                return False
            else:
                return True
        self.error(f"DA_Send status error:{self.eh.status(status)}")
        return False
