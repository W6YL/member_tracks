# Wiegand Converter

The arduino is used in-between the HID ThinLine II reader, and the computer, as an interface to convert the data from Wiegand format to a custom Serial format readable by a computer. To decode this data, we will be using the library https://github.com/paulo-raca/YetAnotherArduinoWiegandLibrary. 

### Protocol
This is the protocol definition for the serial communications from Arduino -> Computer

Each packet begins with a 1 byte header indicating the packet type, providing up to 256 possible types.
Below is a table of each packet type and a brief description of what it does.
| Packet ID         |     Description      | Size (bytes)  |
| :---------------- | :------------------: | ------------: |
| 0x01              | Connect State Change | 2             |
| 0x02              | Reader Data          | variable      |

#### (0x01) Connect State Change Packet
The Connect state change packet indicates the connection state between the arduino and the HID reader.
`0x00` = Disconnected, `0x01` = Connected
Example Packet: `0x01 0x01` (Connect state change + CONNECTED status)

#### (0x02) Reader Data Packet
The Reader Data packet is sent when a card is placed against the reader and successfully read. It contains the raw bytes read from the card. It is prefixed by a single byte header including the length of the following bytes to be read.

The following is an example of a packet which contains the raw bytes "0x01 0x02 0x03 0x04"
| Example Byte(s)     |     Description      | Size (bytes)  |
| :------------------ | :------------------: | ------------: |
| 0x02                | Packet Header (Type indicator)| 1 |
| 0x04                | Size of the following data | 1             |
| 0x01 0x02 0x03 0x04 | Read Data          | variable (0x04)      |
Entire Packet Data (hex): `020401020304`
