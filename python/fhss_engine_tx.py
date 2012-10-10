#
# Copyright 1980-2012 Free Software Foundation, Inc.
# 
# This file is part of GNU Radio
# 
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

import numpy
from math import pi
from gnuradio import gr
from gruel import pmt
from gnuradio.digital import packet_utils
import gnuradio.digital as gr_digital
import gnuradio.extras #brings in gr.block
import Queue
import time
import math
import gnuradio.extras as gr_extras


BROADCAST_ADDR = 255

#block port definitions - inputs
OUTGOING_PKT_PORT = 0
CTRL_PORT = 1

#block port definitions - outputs
TO_FRAMER_PORT = 0
CTRL_PORT = 1

#Time state machine
LOOKING_FOR_TIME = 0 
HAVE_TIME = 0

#RX state machine
RX_INIT = 0 
RX_SEARCH = 1
RX_FOUND = 2

#other
LOST_SYNC_THRESHOLD = 5

#Protocol Fields
HAS_DATA = numpy.ones( ( 1, 1),dtype='uint8')[0]
HAS_NO_DATA = numpy.zeros( ( 1, 1),dtype='uint8')[0]

# /////////////////////////////////////////////////////////////////////////////
#                   TDMA MAC
# /////////////////////////////////////////////////////////////////////////////

class fhss_engine_tx(gr.block):
    """
    FHSS implementation.  See wiki for more details
    """
    def __init__(
        self,hop_interval,post_guard,pre_guard,tx_freq_list,lead_limit,link_bps
    ):
        """
        Inputs: complex stream from USRP, pkt in, ctrl in
        Outputs: pkt out, ctrl out
        """

        gr.block.__init__(
            self,
            name = "fhss_engine_tx",
            in_sig = [numpy.complex64],
            out_sig = None,
            num_msg_inputs = 3,
            num_msg_outputs = 3,
        )
    
        self.mgr = pmt.pmt_mgr()
        for i in range(64):
            self.mgr.set(pmt.pmt_make_blob(10000))
        
        self.hop_interval = hop_interval
        self.post_guard = post_guard
        self.pre_guard = pre_guard
        self.lead_limit = lead_limit
        self.link_bps = link_bps
        self.tx_freq_list = map(float,tx_freq_list.split(','))
        self.tx_freq_list_length = len(self.tx_freq_list)
        self.hop_index = 0 
        
        self.bytes_per_slot = int( ( self.hop_interval - self.post_guard - self.pre_guard ) * self.link_bps / 8 )
        
        self.queue = Queue.Queue()                        #queue for msg destined for ARQ path
        self.tx_queue = Queue.Queue()
        
        self.last_rx_time = 0
        self.last_rx_rate = 0
        self.samples_since_last_rx_time = 0
        
        self.next_interval_start = 0
        self.next_transmit_start = 0

        self.know_time = False
        self.found_time = False
        self.found_rate = False
        self.set_tag_propagation_policy(gr_extras.TPP_DONT)    

        self.has_old_msg = False
        self.overhead = 20
        self.pad_data = numpy.zeros( ( 1, 1500),dtype='uint8')[0]
        #print self.pad_data
        self.tx_slots_passed = 0
    
        self.rx_state = RX_SEARCH
        self.plkt_received = False
        self.tune_lead = 0.003
        self.rx_hop_index = 0
        self.consecutive_miss = 0
        
        
    
    def tx_frames(self):
        #send_sob
        #self.post_msg(TO_FRAMER_PORT, pmt.pmt_string_to_symbol('tx_sob'), pmt.PMT_T, pmt.pmt_string_to_symbol('tx_sob'))


        #get all of the packets we want to send
        total_byte_count = 0
        frame_count = 0
        a = pmt.from_python( ( ( self.tx_freq_list[self.hop_index] , ), { } ) )
        self.post_msg(CTRL_PORT,pmt.pmt_string_to_symbol('usrp_sink.set_command_time'),pmt.from_python( ( ( self.interval_start , ), { } ) ),pmt.pmt_string_to_symbol('fhss'))
        self.post_msg(CTRL_PORT,pmt.pmt_string_to_symbol('usrp_sink.set_center_freq'),pmt.from_python( ( ( self.tx_freq_list[self.hop_index] , ), { } ) ),pmt.pmt_string_to_symbol('fhss'))
        self.post_msg(CTRL_PORT,pmt.pmt_string_to_symbol('usrp_sink.clear_command_time'),pmt.from_python( ( ( 0 , ), { } ) ),pmt.pmt_string_to_symbol('fhss'))
        self.hop_index = ( self.hop_index + 1 ) % self.tx_freq_list_length
        #print self.hop_index,self.interval_start
        
        #put residue from previous execution
        if self.has_old_msg:
            length = len(pmt.pmt_blob_data(self.old_msg.value)) + self.overhead
            total_byte_count += length
            self.tx_queue.put(self.old_msg)
            frame_count += 1
            self.has_old_msg = False
            print 'old msg'

        #fill outgoing queue until empty or maximum bytes queued for slot
        while(not self.queue.empty()):
            msg = self.queue.get()
            length = len(pmt.pmt_blob_data(msg.value)) + self.overhead
            total_byte_count += length
            if total_byte_count >= self.bytes_per_slot:
                self.has_old_msg = True
                self.old_msg = msg
                print 'residue'
                continue
            else:
                self.has_old_msg = False
                self.tx_queue.put(msg)
                frame_count += 1
        
        time_object = int(math.floor(self.antenna_start)),(self.antenna_start % 1)
        
        #if no data, send a single pad frame
        #TODO: add useful pad data, i.e. current time of SDR
        if frame_count == 0:
            data = numpy.concatenate([HAS_NO_DATA,self.pad_data])
            more_frames = 0
            tx_object = time_object,data,more_frames
            self.post_msg(TO_FRAMER_PORT,pmt.pmt_string_to_symbol('full'),pmt.from_python(tx_object),pmt.pmt_string_to_symbol('tdma'))
        else:
            #print frame_count,self.queue.qsize(), self.tx_queue.qsize()
            #send first frame w tuple for tx_time and number of frames to put in slot
            blob = self.mgr.acquire(True) #block
            more_frames = frame_count - 1
            msg = self.tx_queue.get()
            data = numpy.concatenate([HAS_DATA,pmt.pmt_blob_data(msg.value)])
            tx_object = time_object,data,more_frames
            self.post_msg(TO_FRAMER_PORT,pmt.pmt_string_to_symbol('full'),pmt.from_python(tx_object),pmt.pmt_string_to_symbol('tdma'))
            frame_count -= 1
            
            
            old_data = []
            #print 'frame count: ',frame_count
            #send remining frames, blob only
            while(frame_count > 0):
                msg = self.tx_queue.get()
                data = numpy.concatenate([HAS_DATA,pmt.pmt_blob_data(msg.value)])
                blob = self.mgr.acquire(True) #block
                pmt.pmt_blob_resize(blob, len(data))
                pmt.pmt_blob_rw_data(blob)[:] = data
                self.post_msg(TO_FRAMER_PORT,pmt.pmt_string_to_symbol('d_only'),blob,pmt.pmt_string_to_symbol('tdma'))
                frame_count -= 1
        
        #print total_byte_count
        
    def work(self, input_items, output_items):
        
        if self.rx_state == RX_INIT:
            self.post_msg(CTRL_PORT,pmt.pmt_string_to_symbol('usrp_source.set_center_freq'),pmt.from_python( ( ( self.rx_freq_list[self.rx_hop_index] , ), { } ) ),pmt.pmt_string_to_symbol('fhss'))
            self.rx_state == RX_SEARCH
        
        
        #check for msg inputs when work function is called
        if self.check_msg_queue():
            try: msg = self.pop_msg_queue()
            except: return -1

            if msg.offset == OUTGOING_PKT_PORT:
                self.queue.put(msg)                 #if outgoing, put in queue for processing

            else:
                a = 0                               #CONTROL port
            
        #process streaming samples and tags here
        in0 = input_items[0]
        nread = self.nitems_read(0) #number of items read on port 0
        ninput_items = len(input_items[0])

        #read all tags associated with port 0 for items in this work function
        tags = self.get_tags_in_range(0, nread, nread+ninput_items)

        #lets find all of our tags, making the appropriate adjustments to our timing
        for tag in tags:
            key_string = pmt.pmt_symbol_to_string(tag.key)
            if key_string == "rx_time":
                self.samples_since_last_rx_time = 0
                self.current_integer,self.current_fractional = pmt.to_python(tag.value)
                self.time_update = self.current_integer + self.current_fractional
                self.found_time = True
            elif key_string == "rx_rate":
                self.rate = pmt.to_python(tag.value)
                self.sample_period = 1/self.rate
                self.found_rate = True
        
        #determine first transmit slot when we learn the time
        if not self.know_time:
            if self.found_time and self.found_rate:
                self.know_time = True
                #TODO: this stuff is left over from tdma.py, see if we can re-use this somehow
                #self.frame_period = self.slot_interval * self.num_slots
                #my_fraction_frame = ( self.initial_slot * 1.0 ) / ( self.num_slots)
                #frame_count = math.floor(self.time_update / self.frame_period)
                #current_slot_interval = ( self.time_update % self.frame_period ) / self.frame_period
                #self.time_transmit_start = (frame_count + 2) * self.frame_period + ( my_fraction_frame * self.frame_period ) - self.lead_limit
                self.time_transmit_start = self.time_update + ( self.lead_limit * 10.0 )
                self.interval_start = self.time_transmit_start + self.lead_limit
        
        #get current time
        self.time_update += (self.sample_period * ninput_items)

        #determine if it's time for us to start tx'ing, start process self.lead_limit seconds
        #before our slot actually begins (i.e. deal with latency)
        if self.time_update > self.time_transmit_start:
            self.antenna_start = self.interval_start + self.post_guard
            self.tx_frames()  #do more than this?
            self.interval_start += self.hop_interval
            self.time_transmit_start = self.interval_start - self.lead_limit
            


        
        return ninput_items
        
