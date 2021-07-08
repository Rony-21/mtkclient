# mtkclient
Just some mtk tool for exploitation, reading/writing flash and doing crazy stuff. For linux, a patched kernel is needed (see Setup folder) (except for read/write flash).
For windows, you need to install zadig driver and replace pid 0003 / pid 2000 driver.

Once the mtk.py script is running, boot into brom mode by powering off device, press and hold either
vol up + power or vol down + power and connect the phone. Once detected by the tool,
release the buttons.

## Installation

### Use Re LiveDVD (everything ready to go):
[Download Re Live DVD](https://drive.google.com/file/d/1aroCr2VaXON6fWB6G8R1sz8wMvSbleck/view?usp=sharing)
User: livedvd, Password:livedvd

### Use FireISO as LiveDVD:
[Download FireIso Live DVD](https://github.com/amonet-kamakiri/fireiso/releases/tag/v2.0.0)

### Install python >=3.8

```
sudo apt install python3
pip3 install -r requirements.txt
```

### Install rules
```
sudo adduser $USER dialout
sudo adduser $USER plugdev
sudo cp Setup/Linux/*.rules /etc/udev/rules.d
sudo udevadm control -R
```

### Install gcc armeabi compiler

```
sudo apt-get install gcc-arm-none-eabi
```

### Compile patched kernel (if you don't use FireISO)

- For linux (kamakiri attack), you need to recompile your linux kernel using this kernel patch :
```
sudo apt-get install build-essential libncurses-dev bison flex libssl-dev libelf-dev libdw-dev
git clone https://git.kernel.org/pub/scm/devel/pahole/pahole.git
cd pahole && mkdir build && cd build && cmake .. && make && sudo make install
sudo mv /usr/local/libdwarves* /usr/local/lib/ && sudo ldconfig
```

```
wget https://cdn.kernel.org/pub/linux/kernel/v5.x/linux-`uname -r`.tar.xz
tar xvf linux-`uname -r`.tar.xz
cd linux-`uname -r`
patch -p1 < ../Setup/Linux/kernelpatches/disable-usb-checks-5.10.patch
cp -v /boot/config-$(uname -r) .config
make menuconfig
make
sudo make modules_install 
sudo make install
```

- These aren't needed for current ubuntu (as make install will do, just for reference):

```
sudo update-initramfs -c -k `uname -r`
sudo update-grub
```

See Setup/kernels for ready-to-use kernel setups


- Reboot

```
sudo reboot
```

## Usage

### Bypass SLA, DAA and SBC (using generic_patcher_payload)
`` 
./mtk.py payload
`` 
If you want to use SP Flash tool afterwards, make sure you select "UART" in the settings, not "USB".

### Dump brom
- Device has to be in bootrom mode, or da mode has to be crashed to enter damode
- if no option is given, either kamakiri or da will be used (da for insecure targets)
- if "kamakiri" is used as an option, kamakiri is enforced
- Valid options are : "kamakiri" (via usb_ctrl_handler attack), "amonet" (via gcpu)
  and "hashimoto" (via cqdma)

```
./mtk.py dumpbrom --ptype=["amonet","kamakiri","hashimoto"] [--filename=brom.bin]
```

### Run original/patched preloader and disable sbc
- Boot in Brom or crash to Brom
```
./mtk.py plstage --preloader=preloader.bin
```

### Read memory using patched preloader
- Boot in Brom or crash to Brom
```
./mtk.py peek [addr] [length] --preloader=patched_preloader.bin
```

### Run custom payload

```
./mtk.py payload --payload=payload.bin [--var1=var1] [--wdt=wdt] [--uartaddr=addr] [--da_addr=addr] [--brom_addr=addr]
```

### Run stage2 in bootrom
`` 
./mtk.py stage
`` 

### Run stage2 in preloader
`` 
./mtk.py plstage
`` 

### Read rpmb in stage2 mode
`` 
./stage2.py --rpmb
`` 

### Read preloader in stage2 mode
`` 
./stage2.py --preloader
`` 

### Read memory as hex data in stage2 mode
`` 
./stage2.py --memread --start 0x0 --length 0x16
`` 

### Read memory to file in stage2 mode
`` 
./stage2.py --memread --start 0x0 --length 0x16 --filename brom.bin
`` 

### Write hex data to memory in stage2 mode
`` 
./stage2.py --memwrite --start 0x0 --data 12345678AABBCCDD
`` 

### Write memory from file in stage2 mode
`` 
./stage2.py --memwrite --start 0x0 --filename brom.bin
`` 

### Crash da in order to enter brom

```
./mtk.py crash [--vid=vid] [--pid=pid] [--interface=interface]
```

### Read flash

Dump boot partition to filename boot.bin via preloader

```
./mtk.py r boot boot.bin
```

Dump boot partition to filename boot.bin via bootrom

```
./mtk.py r boot boot.bin --preloader=Loader/Preloader/your_device_preloader.bin
```


Read full flash to filename flash.bin (use --preloader for brom)

```
./mtk.py rf flash.bin
```

Dump all partitions to directory "out". (use --preloader for brom)

```
./mtk.py rl out
```

Show gpt (use --preloader for brom)

```
./mtk.py printgpt
```


### Write flash
(use --preloader for brom)

Write filename boot.bin to boot partition

```
./mtk.py w boot boot.bin
```

Write filename flash.bin as full flash (currently only works in da mode)

```
./mtk.py wf flash.bin
```

Write all files in directory "out" to the flash partitions

```
./mtk.py wl out
```

### Erase flash

Erase boot partition (use --preloader for brom)
```
./mtk.py e boot
```


### I need logs !

- Run the mtk.py tool with --debugmode. Log will be written to log.txt (hopefully)

## Rules / Infos

### Chip details / configs
- Go to config/brom_config.py
- Unknown usb vid/pids for autodetection go to config/usb_ids.py
