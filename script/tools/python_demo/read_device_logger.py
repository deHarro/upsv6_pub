from smbus2 import SMBus
import time 
from datetime import datetime


# Device address  
DEVICE_ADDRESS = 0x17

# init SMBus
bus = SMBus(1)  # 1 means I2C no.1 bus


# Define registers address
# WHO_AM_I_REG = 0x00 // will always be 0xA6
VERSION_REG = 0x01              #  8bit - R
UID0_REG = 0x02                 # 32bit - R
UID1_REG = 0x06                 # 32bit - R
UID2_REG = 0x0A                 # 32bit - R
OUTPUT_VOLTAGE_REG = 0x0E       # 16bit - R
INPUT_VOLTAGE_REG = 0x10        # 16bit - R
BATTERY_VOLTAGE_REG = 0x12      # 16bit - R
MCU_VOLTAGE_REG = 0x14          # 16bit - R
OUTPUT_CURRENT_REG = 0x16       # 16bit - R
INPUT_CURRENT_REG = 0x18        # 16bit - R
BATTERY_CURRENT_REG = 0x1A      # 16bit - R
TEMPERATURE_REG = 0x1C          #  8bit - R
CONTROL1_REG = 0x1D             #  8bit - R/W
CONTROL2_REG = 0x1E             #  8bit - R/W (reserved)
STATUS1_REG = 0x1F              #  8bit - R
STATUS2_REG = 0x20              #  8bit - R
BATT_PROT_VOLT_REG = 0x21       # 16bit - R/W (mV)
SHUTDWN_COUNTR_REG = 0x23       # 16bit - R/W (seconds)
AUTOSTART_VOLT_REG = 0x25       # 16bit - R/W (mV)
PYTHON_BUF_LEN_REG = 0x27       # 16bit - R/W
OTA_REQUEST_REG = 0x29          # 16bit - W   (0xA5A5 -> FW update mode, OTA mode)
RUNTIME_REG = 0x2B              # 64bit - R   (overall runtime, microseconds)
CHARGEDETECT_INTERVAL = 0x33    # 16bit - R/W (seconds)

# Define ANSI color
RED = '\033[95m'
GREEN = '\033[92m'
END_COLOR = '\033[0m'

# Define log file name
LOG_FILENAME = './runtime_log_ups.txt'

# read 8bit register 
def read_byte_register(register_address):
    value = bus.read_byte_data(DEVICE_ADDRESS, register_address)
    if value > 127:
        value -= 256 
    return value

# read 16bit register 
def read_word_register(register_address):
    value = bus.read_word_data(DEVICE_ADDRESS, register_address)
    if value > 32767:
        value -= 65536
    return value

# read 32bit register 
def read_dword_register(register_address):
    low = bus.read_word_data(DEVICE_ADDRESS, register_address)
    high = bus.read_word_data(DEVICE_ADDRESS, register_address + 2)
    return (high << 16) | low

# read all registers data
def read_all_registers():
    registers = {
        "WHO_AM_I": "0xA6",
        "VERSION": read_byte_register(VERSION_REG),
        "UID0": read_dword_register(UID0_REG),
        "UID1": read_dword_register(UID1_REG),
        "UID2": read_dword_register(UID2_REG),
        "OUTPUT_VOLTAGE": read_word_register(OUTPUT_VOLTAGE_REG),
        "INPUT_VOLTAGE": read_word_register(INPUT_VOLTAGE_REG),
        "BATTERY_VOLTAGE": read_word_register(BATTERY_VOLTAGE_REG),
        "MCU_VOLTAGE": read_word_register(MCU_VOLTAGE_REG),
        "OUTPUT_CURRENT": read_word_register(OUTPUT_CURRENT_REG),
        "INPUT_CURRENT": read_word_register(INPUT_CURRENT_REG),
        "BATTERY_CURRENT": read_word_register(BATTERY_CURRENT_REG),
        "TEMPERATURE": read_byte_register(TEMPERATURE_REG)
    }
    return registers

# read and print out all registers data.
try:
    while True:
        print(f"{RED}=== 52Pi UPS V6 Raw Data Output ==={END_COLOR}")
        registers = read_all_registers()
        with open(LOG_FILENAME, "a") as f:
            f.write(f"-------------{datetiget_py_output me.now()}-----------\n")  # log start
        for key, value in registers.items():
            if "VOLTAGE" in key:
                print(f"* {key}: {GREEN}{value}mV{END_COLOR} ")
                with open(LOG_FILENAME, "a") as f:
                    f.write(f"* {key}: {value}mV\n")
            elif "CURRENT" in key:
                print(f"* {key}: {RED}{value}mA{END_COLOR} ")
                with open(LOG_FILENAME, "a") as f:
                    f.write(f"* {key}: {value}mA\n")
            elif "TEMPERATURE" in key:
                print(f"* {key}: {GREEN}{value}℃{END_COLOR} ")
                with open(LOG_FILENAME, "a") as f:
                    f.write(f"* {key}: {value}℃\n")
            elif "WHO_AM_I" in key:
                print(f"* {key}: {value}")
            else:
                print(f"* {key}: {value}")
        with open(LOG_FILENAME, "a") as f:
            f.write("-"* 80) # log end
            f.write("\n")
        print("-"*80)
        print(" "*80)
        time.sleep(2)  # flush interval in 2 seconds
except KeyboardInterrupt:
    # Shutdown SMBus
    bus.close()
    print("Quit Demo")

