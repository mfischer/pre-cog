#!/usr/bin/env python

import gnuradio.extras as gr_extras
from gnuradio import gr
from gruel import pmt
import precog
import numpy
import Queue

##############################3
# DEFINITIONS
##############################3

RADIO_PORT = 0
APP_PORT = 1
CTRL_PORT = 2

#Packet index definitions
PKT_INDEX_CTRL = 4
PKT_INDEX_PROT_ID = 3
PKT_INDEX_DEST = 2
PKT_INDEX_SRC = 1
PKT_INDEX_CNT = 0
PKT_INDEX_ACK = 5

USER_IO_PROTOCOL_ID = 92
USER_IO_MULTIPLEXED_ID = 93

ARQ_PROTOCOL_ID = 90
BROADCAST_PROTOCOL_ID = 91


KEY_INDEX_CTRL = 0
KEY_INDEX_DEST_ADDR = 1

ARQ_REQ = 85
ARQ_NO_REQ = 86

MAX = 255



def get_dest_from_key(keystr):
    return ord(keystr[KEY_INDEX_DEST_ADDR])


class selective_arq_receiver(object):
    def __init__(self, addr, rx_wsz, to_phy, up):
        self.addr = addr
        self.rx_wsz = rx_wsz
        self.to_phy = to_phy
        self.pass_up = up
        self.rx_count = 0
        self.rx_buf = {}

    def send_ack(self, seq_no, dest):
        msg = chr(seq_no)
        pkt_str = chr(self.rx_count) + chr(self.addr) + chr(dest) + \
                  chr(ARQ_PROTOCOL_ID) + chr(ARQ_NO_REQ) + msg
        self.to_phy(pkt_str)

    def receive_data(self, data):
        seq_no = data[PKT_INDEX_CNT]
        src = data[PKT_INDEX_SRC]
        if seq_no == self.rx_count:
            self.send_ack(self.rx_count, src)
            self.rx_count += 1
            self.rx_count %= MAX
            self.pass_up(data)
            while(self.rx_buf.has_key(self.rx_count)):
                self.send_ack(self.rx_count, src)
                self.pass_up(self.rx_buf.pop(self.rx_count))

        elif (seq_no > self.rx_count) and seq_no < self.rx_count + self.rx_wsz:
            self.rx_buf[seq_no] = data
            self.send_ack(self.rx_count, src)

        elif (seq_no < self.rx_count) and (seq_no < (self.rx_count + self.rx_wsz) % MAX):
            self.rx_buf[seq_no] = data
            self.send_ack(self.rx_count, src)

        else:
            self.send_ack(self.rx_count, src)



class selective_arq_transmitter(object):
    def __init__(self, addr, tx_wsz, to_phy):
        self.addr = addr
        self.tx_wsz = tx_wsz
        self.to_phy = to_phy
        self.tx_buf = []
        self.tx_count = 0
        self.ack_count = 0

    def receive_ack(self, data):
        seq_no = data[PKT_INDEX_CNT]
        if self.ack_count < seq_no:
            ackd_packets = int(seq_no - self.ack_count)
            self.ack_count = seq_no
            self.tx_buf = self.tx_buf[ackd_packets:]
        elif seq_no < ((self.ack_count + self.tx_wsz) % MAX):
            ackd_packets = int(abs(seq_no - self.ack_count))
            self.ack_count = seq_no
            self.tx_buf = self.tx_buf[ackd_packets:]


    def is_busy(self):
        return self.tx_count >= (self.ack_count + self.tx_wsz % MAX)

    def transmit(self, msg, dest, protocol_id, control):
        if type(msg) is not str:
            pkt_str = chr(self.tx_count) + chr(self.addr) + chr(dest) + \
                      chr(protocol_id) + chr(control) + \
                      pmt.pmt_blob_data(msg.value).tostring()
        else:
            pkt_str = chr(self.tx_count) + chr(self.addr) + chr(dest) + \
                      chr(protocol_id) + chr(control) + msg
        self.tx_buf.append(pkt_str)
        self.tx_count += 1
        self.tx_count %= MAX

        self.to_phy(pkt_str)

    def transmit_missing(self):
        if not (self.ack_count == self.tx_count):
            for pkt in self.tx_buf:
                self.to_phy(pkt)


class selective_arq_mac(gr.block):
    """
    This block implements a sliding window protocol,
    it works roughly like this:

    The transmitter is allowed to send up to tx_wsz packets more than he got ACK'd.
    In case one of the packets get lost, the receiver will continue to receive up to
    rx_wsz packets more than the last one he should have received.
    The receiver will send an ACK for the last in-sequence packet to the transmitter,
    which will allow the transmitter to remove the packet from its transmit buffer
    upon reception of an ACK.
    """

    def __init__(self, addr, tx_wsz=128, rx_wsz=42, name='selective_arq_mac'):
        self.receiver = selective_arq_receiver(addr, rx_wsz, self.to_lower_layer, self.to_upper_layer)
        self.transmitter = selective_arq_transmitter(addr, tx_wsz, self.to_lower_layer)

        self.receive_ack = self.transmitter.receive_ack
        self.receive_data = self.receiver.receive_data
        self.transmit_missing = self.transmitter.transmit_missing
        self.is_busy = self.transmitter.is_busy

        gr.block.__init__(self, name = name, in_sig = None,
                          out_sig = None, num_msg_inputs = 3,
                          num_msg_outputs = 3)

        self.mgr = pmt.pmt_mgr()
        for i in range(64):
            self.mgr.set(pmt.pmt_make_blob(10000))

        self.queue = Queue.Queue()

    def to_lower_layer(self, pkt_str):
	"""
	This function describes how data gets pushed to the lower (PHY) layer.
	One can just subclass this class to add custom ways to do this.
	"""
        blob = self.mgr.acquire(True) #block
        pmt.pmt_blob_resize(blob, len(pkt_str))
        pmt.pmt_blob_rw_data(blob)[:] = numpy.fromstring(pkt_str, dtype='uint8')
        self.post_msg(0, pmt.pmt_string_to_symbol('U'), blob)

    def to_upper_layer(self, payload):
	"""
	This function describes how data gets pushed to the next higher layer.
	One can just subclass this class to add custom ways to do this.
	"""
        payload_len = len(payload)
        if (payload_len > 5):
            payload = payload[5:]
        #print '[%s] data %s' % (self.name(), str(payload))
        blob = self.mgr.acquire(True)
        pmt.pmt_blob_resize(blob, len(payload))
        pmt.pmt_blob_rw_data(blob)[:] = payload
        self.post_msg(1, pmt.pmt_string_to_symbol('U'), blob)

    def work(self, input_items, output_items):
	"""
	This is the work function ... every gr.block should have one.
	"""

        while(1):
            try: msg = self.pop_msg_queue()
            except: return -1

            if not pmt.pmt_is_blob(msg.value):
                #print '[%s] not a blob' % self.name()
                continue

            # we received something on the app port
            if msg.offset == APP_PORT:
                #print '[%s] queueing msg ...' % self.name()
                self.queue.put(msg)

            # we received something on the radio port
            elif msg.offset == RADIO_PORT:
                data = pmt.pmt_blob_data(msg.value)

                # it's an ACK
                if data[PKT_INDEX_PROT_ID] == ARQ_PROTOCOL_ID:
                    self.receive_ack(data)
                # it's userdata
                else:
                    self.receive_data(data)

            # we received something on the ctrl port
            elif msg.offset == CTRL_PORT:
                pass

            else:
                print '[%s] w00t, weird msg offset' % self.name()


            if (not self.queue.empty()) and (not self.is_busy()):
                msg = self.queue.get_nowait()
                keystr = pmt.pmt_symbol_to_string(msg.key)
                #print '[%s] queue_size = %u' % (self.name(), self.queue.qsize())
                dest = get_dest_from_key(keystr)
                self.transmitter.transmit(msg, dest, USER_IO_PROTOCOL_ID, ARQ_REQ)

            if self.is_busy():
                self.transmit_missing()

#            print '[%s] Is busy?' % self.name() , self.is_busy()

class mactest(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self)
        self.mac0 = selective_arq_mac(42,128,30,'mac0')
        self.mac1 = selective_arq_mac(43,128,30,'mac1')
        self.formatter = precog.virtual_channel_formatter(86,1)
        self.heartbeat = precog.heart_beat(1,"W","This is a test beacon\n")
        self.null_sink0 = gr.null_sink(gr.sizeof_char*1)
        self.null_sink1 = gr.null_sink(gr.sizeof_char*1)

	self.socket_sink = gr_extras.blob_to_socket('UDP', '127.0.0.1', '12345')

	# Wire up the stuff
        self.connect((self.mac0,0), (self.mac1,0))
        self.connect((self.mac1,0), (self.mac0,0))

	self.connect((self.mac0,1), (self.null_sink0, 0))
	self.connect((self.mac1,1), (self.socket_sink, 0))
	#self.connect((self.mac1,1), (self.null_sink1, 0))

        self.connect((self.heartbeat,0), (self.formatter,0), (self.mac0,1))

if __name__ == '__main__':
	tb = mactest()
	tb.run(True)
