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



# /////////////////////////////////////////////////////////////////////////////
#                   Virtual Channel Formatter
# /////////////////////////////////////////////////////////////////////////////

class virtual_channel_demux(gr.block):
    """
    Examine header byte and route to appropriate output
    """
    def __init__(
        self,port_count
    ):
        """
        The input is a pmt message blob.
        Output are message blobs
        """

        gr.block.__init__(
            self,
            name = "virtual_channel_demux",
            in_sig = None,
            out_sig = None,
            num_msg_inputs = 1,
            num_msg_outputs = port_count,
        )
    
        self.mgr = pmt.pmt_mgr()
        for i in range(64):
            self.mgr.set(pmt.pmt_make_blob(10000))
            
        self.port_count = port_count
        
    def work(self, input_items, output_items):
        
        while(1):
            try: msg = self.pop_msg_queue()
            except: return -1
            
            if not pmt.pmt_is_blob(msg.value): 
                print "not a blob - virtual demux"
                continue

            incoming_array = pmt.pmt_blob_data(msg.value)
            outgoing_array = incoming_array[1:]
            
            output_port = int(incoming_array[0])

            #check to make sure the byte header is within our valid range
            if  ( output_port > ( self.port_count - 1 ) ):
                print 'received msg outside of port range'
                continue

            blob = self.mgr.acquire(True) #block
            pmt.pmt_blob_resize(blob, len(outgoing_array))
            pmt.pmt_blob_rw_data(blob)[:] = outgoing_array
            self.post_msg(output_port,pmt.pmt_string_to_symbol('n/a'),blob,pmt.pmt_string_to_symbol('demux'))
