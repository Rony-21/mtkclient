# MTK Research Repo
brought to you by B.Kerler (viperbjk) and k4y0z (Chaosmaster), main exploit by @xyzz (amonet and kamakiri)

All the stuff in here is currently private. We will develop new features and new attacks,
some will be shared with the hacking community :)

## Install

### Grab python >=3.8

```
sudo apt install python3
pip3 install -r requirements.txt
```

### Install gcc armeabi compiler

```
sudo apt-get install gcc-arm-none-eabi
```

### Compile payloads

See src/readme.build for detailed instructions.

```
cd src
make
```

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
patch -p1 < ../Setup/kernelpatches/disable-usb-checks-5.10.patch
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

```
./mtk.py payload
```

### Run custom payload

```
./mtk.py payload --payload=payload.bin [--var1=var1] [--wdt=wdt] [--uartaddr=addr] [--da_addr=addr] [--brom_addr=addr]
```

### Dump brom
- Device has to be in bootrom mode, or da mode has to be crashed to enter damode
- if no option is given, either kamakiri or da will be used (da for insecure targets)
- if "kamakiri" is used as an option, kamakiri is enforced
- Valid options are : "kamakiri" (via usb_ctrl_handler attack), "amonet" (via gcpu) and
                      "hashimoto" (via cqdma)

```
./mtk.py dumpbrom --ptype=["amonet","kamakiri","hashimoto"] [--filename=brom.bin]
```

### Crash da in order to enter brom

```
./mtk.py crash [--vid=vid] [--pid=pid] [--interface=interface]
```

### Read flash

Dump boot partition to filename boot.bin (currently only works in da mode)

```
./mtk.py r boot boot.bin
```

Read full flash to filename flash.bin (currently only works in da mode)

```
./mtk.py rf flash.bin
```

Dump all partitions to directory "out". (currently only works in da mode)

```
./mtk.py rl out
```

Show gpt (currently only works if device has gpt)

```
./mtk.py printgpt
```

### Run stage 2

1. Install in brom mode via kamakiri

```
./mtk.py stage
```

1. or install in preloader mode via send_da:

Show gpt (currently only works if device has gpt)

```
./mtk.py plstage
```

2. Run stage2 tools

#### Read rpmb
```
./stage2.py -rpmb
```

#### Read preloader
```
./stage2.py -preloader
```

#### Dump memory as hex
```
./stage2.py -readmem [addr] [length]
```

#### Write memory as hex
```
./stage2.py -writemem [addr] [length] [hexstring]
```


## Rules / Infos

### Chip details / configs
- Go to config/brom_config.py
- Unknown usb vid/pids for autodetection go to config/usb_ids.py

### Additional Tools

#### Main tools :
- Tools/brom_to_offs.py -> For automated offset/function finding for brom exploit
- Tools/emulate_payload.py -> Emulate payload to see if payload works in brom as expected
- Tools/da_parser.py -> In order to parse MTK proprietary tools / structures

#### Sign Tee and trustlets
- See Tools/Signer/mtksign.py for signing
- See Tools/Signer/rss_verify.py for key checks

### ToDos :
- Add amonet payload support
- Add HUK/Serial/RPMB Key extraction
- Add Footer/Userdata decryption
- Add support of custom ramdisks (boot)
- Add/verify write function
- Fix read for bootrom mode (DA mode works)
- Replace proprietary AllInOne DA Loaders with own custom DA Loaders
- Find more brom-exploits and DA-crashes
- Modem emulation, tools
- Add Jtag stuff
- Include Windows Driver Auto-Installer
- 6580 DA works, but kamakiri fails
- 6582 completely fails

### Where do I put my bootroms ?

- Copy them into the bootrom directory [chipname]_[chipcode/hwcode].bin, for example : "mt6761_717.bin"
  Bootroms will be shared only in this group and will NOT be made public.


### I need logs !

- Run the mtk.py tool with --debugmode. Log will be written to log.txt (hopefully)
