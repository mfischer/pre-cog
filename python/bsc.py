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

import time

from gnuradio import gr
from gruel import pmt

class bsc(gr.block):
    """
    This block implements a BSC (binary symmetric channel,
    for use with the MACs in Pre-Cog.

    It has two parameters, the intended BER (bit error rate),
    and the number of the bits that are used in the one byte
    input messages.
    """
    def __init__(self, ber=0.01, bits_per_byte=1):
        gr.block.__init__(self, name='bsc' ,in_sig = None,
                          out_sig = None, num_msg_inputs = 1,
                          num_msg_outputs = 1)
        self.ber = ber
        self.bits_per_byte = bits_per_byte

        self.mgr = pmt.pmt_mgr()
        for i in range(64):
            self.mgr.set(pmt.pmt_make_blob(10000))


    def work(self, input_items, output_items):
        """
        For each message we receive, we generate for each of its
        bits a uniformly distributed random number and see if it
        is smaller than the threshold given by BER.
        """
        while(1):
            try: msg = self.pop_msg_queue()
            except: return -1

            if not pmt.pmt_is_blob(msg.value):
                print '[%s] not a blob' % self.name()
                continue

            if msg.offset == 0:
                data = pmt.pmt_blob_data(msg.value)
                for b in range(self.bits_per_byte):
                    if random.random() < self.ber:
                        data ^= (0x01 << b)
                blob = self.mgr.acquire(True)
                pmt.pmt_blob_resize(blob, len(data))
                pmt.pmt_blob_rw_data(blob)[:] = data
                self.post_msg(0, pmt.pmt_string_to_symbol('U'), blob)

            else:
                print '[%s] w00t, weird msg offset' % self.name()
