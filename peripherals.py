from dataclasses import dataclass


@dataclass
class Peripheral:
    wiki_spec_name: str
    gsm_field: str
    gsm_name: str = None

    def __post_init__(self):
        if self.gsm_name is not None:
            return
        self.gsm_name = self.wiki_spec_name.lower()


PERIPHERALS = [
    Peripheral('A-GPS', 'gps'),
    Peripheral('Accelerometer', 'sensors'),
    Peripheral('Barometer', 'sensors'),
    Peripheral('BeiDou', 'gps', 'BDS'),
    Peripheral('Compass', 'sensors'),
    Peripheral('FM Radio', 'radio'),
    Peripheral('Fingerprint', 'sensors'),
    Peripheral('Galileo', 'gps'),
    Peripheral('GLONASS', 'gps'),
    Peripheral('GPS', 'gps', 'Yes'),
    Peripheral('NAVIC', 'gps'),
    Peripheral('SBAS', 'gps'),
    Peripheral('QZSS', 'gps'),
    Peripheral('Gesture sensor', 'sensors', 'gesture'),
    Peripheral('Gyroscope', 'sensors', 'Gyro'),
    Peripheral('MHL', 'usb'),
    Peripheral('MHL 2', 'usb'),
    Peripheral('NFC', 'nfc', 'Yes'),
    Peripheral('Proximity sensor', 'sensors', 'proximity'),
]
