import pyvisa
import argparse
import logging
import datetime
import csv
from time import sleep
from multiprocessing import Process

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
DATA_FORMAT = "%Y-%m-%d_%H:%M:%S"

PARSER = argparse.ArgumentParser(description="input para doc")
# 控制输出
PARSER.add_argument('--voltage', type=float, default=12.2)
# 程序是否前台运行
PARSER.add_argument('--IS_ForeGround_Mode', type=bool, default=False)
# 输出数据文件名称
PARSER.add_argument('--Dada_File', type=str, default='Power_Current_Data.csv')

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=DATA_FORMAT)

Device_IP = "TCPIP0::192.168.1.2::8080::SOCKET"

# 人为限制不允许输出电压大于40V
MAX_VOLTage_PUT = 40

# 根据产品说明书，建议命令之间的延迟最小为30ms, 部分命令需要更长时间, 所以这里设置为40ms
CMD_MIN_INTERVAL_TIME_MS = 40 / 1000


def get_datetime_now():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S %f").split(' ')


class WriteProcess(Process):
    def __init__(self, file_name):
        super(WriteProcess, self).__init__()
        self.file_name = file_name

    def run(self):
        print('测试%s多进程' % self.file_name)

    def write_to_file(self):
        """
        将读取到的电流值，持续写入CSV文件中
        :return: None
        """
        with open(self.file_name, 'w', newline='') as data_file:
            for i in range(100000):
                my_inst.select_current_value()
                write = csv.writer(data_file)
                write.writerow(my_inst.now_current_value)
                sleep(CMD_MIN_INTERVAL_TIME_MS + 10 / 1000)


class CtrlPower:
    # 电源电压模式定义
    SOUR_MODE = {0: "CV",  # 恒压(输出电压不变, 输出电流随负载变化而变化)
                 1: "CC",  # 恒流(输出电流不变, 输出电压随负载变化而变化)
                 2: "CVCP",  # 恒压恒功率(输出电压随给定电压变化, 对应电流自动变化, 以保证输出的功率恒定)
                 3: "CCCP"}  # 恒流恒功率(输出电流随给定电流变化, 对应电压自动变化, 以保证输出的功率恒定)

    # 电源电压给定方式定义
    VOLT_EXTERNAL = {0: "Digital",  # 数字
                     1: "Analog"}  # 模拟

    def __init__(self, is_foreground_mode: bool) -> None:
        """
        初始化
        :param is_foreground_mode: 是否前台运行
        """
        rm = pyvisa.ResourceManager()
        self.is_foreground_mode = is_foreground_mode

        self.instrument = rm.open_resource(Device_IP)
        sleep(1)
        print(f"Connect {Device_IP} Success!")

        self.instrument.write_termination = "\n"
        self.instrument.read_termination = "\n"

        self.device_info: dict = dict()
        self.power_mode: str = ""
        self.volt_external: str = ""
        self.volt_give_value: tuple = tuple()
        self.now_current_value: tuple = ()

        self.select_device_info()

    def select_device_info(self) -> None:
        """
        查看当前设备的信息
        :return: None
        """
        res = self.instrument.query("*IDN?")
        idm_mean = ("manufacturer",  # 设备供应商名称
                    "device_type",  # 设备类型
                    "device_serial_numb",  # 设备序列号
                    "software_version")  # 软件版本
        tmp_res = res.split(',')
        if len(idm_mean) != len(tmp_res):
            print(f"Format Error, place check, raw_str= {res}")
            raise ValueError(f"Format Error, place check, raw_str= {res}")
        else:
            self.device_info = dict(zip(idm_mean, tmp_res))

        if self.is_foreground_mode:
            print(f"Current Device Info: {self.device_info}")
            # logging.INFO(f"Current Device Info: {self.device_info}")

    def select_power_mode(self) -> None:
        """
        查看当前电源的模式
        :return: None
        """
        res = self.instrument.query("MODE?")
        self.power_mode = CtrlPower.SOUR_MODE[int(res)]
        if self.is_foreground_mode:
            print(f"Current Power Mode: {self.power_mode}")

    def set_power_mode(self, input_value: int):
        """
        设置电源模式
        :param input_value: 电源模式值
        :return: None
        """
        if input_value not in CtrlPower.SOUR_MODE.keys():
            print(f"input value error! input_value={input_value}")
            raise ValueError(f"input value error! input_value={input_value}")

        self.instrument.write(f"MODE {input_value}")

    def select_volt_external(self) -> None:
        """
        查询电源的电压模式
        :return: None
        """
        res = self.instrument.query("VOLT:EXT?")
        self.volt_external = CtrlPower.VOLT_EXTERNAL[int(res)]
        if self.is_foreground_mode:
            print(f"Current Voltage External Type: {self.volt_external}")

    def select_volt_value(self) -> None:
        """
        查询当前直流电压给定的电压值
        :return: None
        """
        rst = self.instrument.query("VOLT?")
        self.volt_give_value = (*get_datetime_now(), rst)

        if self.is_foreground_mode:
            print(f"Give Voltage Value: {self.volt_give_value} V")

    def set_volt_value(self, volt_value):
        """
        设置电压值
        :param volt_value: 给定的电压值(单位:V)
        :return: 命令执行结果
        """
        if not isinstance(volt_value, float):
            print(f"input type error, input_type= {type(volt_value)}")
            raise TypeError(f"input type error, input_type= {type(volt_value)}")

        if volt_value < 0.0:
            print(f"input value mast grate than 0V, input_value = {volt_value}")
            raise ValueError(f"input value mast grate than 0V, input_value = {volt_value}")

        if volt_value > MAX_VOLTage_PUT:
            print(f"input value mast less than {MAX_VOLTage_PUT}V, input_value = {volt_value}")
            raise ValueError(f"input value mast less than {MAX_VOLTage_PUT}V, input_value = {volt_value}")

        self.instrument.write(f"VOLT {volt_value}")

    def select_current_value(self) -> None:
        """
        查询当前直流电流的电流值
        :return: None
        """
        rst = self.instrument.query("MEAS:CURR?")
        self.now_current_value = (*get_datetime_now(), rst)

        if self.is_foreground_mode:
            print(f"{datetime.datetime.now()} Now_Current_Value: {self.now_current_value[-1]} A")

    def ctrl_output_on(self) -> None:
        """
        控制开始输出电压、电流， 等效于没有输出时, 按下前面板的“OUT”键盘
        :return: None
        """
        self.instrument.write(f"OUTPut ON")
        if self.is_foreground_mode:
            print(f"Output on finished")

    def ctrl_output_off(self) -> None:
        """
        控制停止输出电压、电流， 等效于有输出时, 再次按下前面板的“OUT”键盘
        :return: None
        """
        self.instrument.write(f"OUTPut OFF")
        if self.is_foreground_mode:
            print(f"Output off finished")


if __name__ == '__main__':
    args = PARSER.parse_args()
    my_inst = CtrlPower(args.IS_ForeGround_Mode)
    my_inst.select_power_mode()
    my_inst.select_volt_external()

    write_process = WriteProcess(args.Dada_File)
    write_process.start()
    write_process.join()

    if my_inst.is_foreground_mode:
        while True:
            option = input('请根据示例输入操作方式："v 12.0"表示调整电压到12.0v \n请输入命令: ')
            cmd_str_list = option.lstrip().rstrip().split(' ')
            cmd_str_first_cmd = cmd_str_list[0].lower()
            cmd_str_value = float(cmd_str_list[1])

            if cmd_str_first_cmd == 'v':
                my_inst.select_volt_value()
                my_inst.set_volt_value(cmd_str_value)
                sleep(CMD_MIN_INTERVAL_TIME_MS + 10 / 1000)
                my_inst.select_volt_value()
                my_inst.ctrl_output_on()
                sleep(CMD_MIN_INTERVAL_TIME_MS + 10 / 1000)
            elif option == 'e':
                print('退出！')
                break
            else:
                print('输入无效，请重新输入')
