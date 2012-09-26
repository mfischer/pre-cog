/*
 * Copyright 2011-2012 Free Software Foundation, Inc.
 * 
 * This file is part of GNU Radio
 * 
 * GNU Radio is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 * 
 * GNU Radio is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with GNU Radio; see the file COPYING.  If not, write to
 * the Free Software Foundation, Inc., 51 Franklin Street,
 * Boston, MA 02110-1301, USA.
 */

#include <gnuradio/extras/add.h>
#include <gr_io_signature.h>
#include <stdexcept>
#include <complex>
#include <volk/volk.h>

using namespace gnuradio::extras;

/***********************************************************************
 * Generic adder implementation
 **********************************************************************/
template <typename type>
struct add_work
{
    size_t multiple(void){return 1;}
    size_t operator()(
        const size_t vlen,
        const gnuradio::block::InputItems &input_items,
        const gnuradio::block::OutputItems &output_items
    ){
        const size_t n_nums = output_items[0].size() * vlen;
        type *out = output_items[0].cast<type *>();
        const type *in0 = input_items[0].cast<const type *>();

        for (size_t n = 1; n < input_items.size(); n++){
            const type *in = input_items[n].cast<const type *>();
            for (size_t i = 0; i < n_nums; i++){
                out[i] = in0[i] + in[i];
            }
            in0 = out; //for next input, we do output += input
        }

        return output_items[0].size();
    }
};

/***********************************************************************
 * Adder implementation with float32 - calls volk
 **********************************************************************/
template <>
struct add_work <float>
{
    size_t multiple(void){return volk_get_alignment();}
    size_t operator()(
        const size_t vlen,
        const gnuradio::block::InputItems &input_items,
        const gnuradio::block::OutputItems &output_items
    ){
        const size_t n_nums = output_items[0].size() * vlen;
        float *out = output_items[0].cast<float *>();
        const float *in0 = input_items[0].cast<const float *>();

        for (size_t n = 1; n < input_items.size(); n++){
            const float *in = input_items[n].cast<const float *>();
            volk_32f_x2_add_32f_a(out, in0, in, n_nums);
            in0 = out; //for next input, we do output += input
        }

        return output_items[0].size();
    }
};

/***********************************************************************
 * Templated adder class
 **********************************************************************/
template <typename type>
class add_generic : public add{
public:
    add_generic(const size_t num_inputs, const size_t vlen):
        block(
            "add generic",
            gr_make_io_signature (num_inputs, num_inputs, sizeof(type)*vlen),
            gr_make_io_signature (1, 1, sizeof(type)*vlen)
        ),
        _vlen(vlen)
    {
        const int alignment_multiple = _work.multiple() / (sizeof(type)*vlen);
        set_output_multiple(std::max(1, alignment_multiple));
    }

    int work(
        const InputItems &input_items,
        const OutputItems &output_items
    ){
        const size_t noutput_items = output_items[0].size();
        return _work(_vlen, input_items, output_items);
    }

private:
    const size_t _vlen;
    add_work<type> _work;
};

/***********************************************************************
 * factory function
 **********************************************************************/
add::sptr add::make_fc32_fc32(const size_t num_inputs, const size_t vlen){
    return gnuradio::get_initial_sptr(new add_generic<float>(num_inputs, 2*vlen));
}

add::sptr add::make_sc32_sc32(const size_t num_inputs, const size_t vlen){
    return gnuradio::get_initial_sptr(new add_generic<int32_t>(num_inputs, 2*vlen));
}

add::sptr add::make_sc16_sc16(const size_t num_inputs, const size_t vlen){
    return gnuradio::get_initial_sptr(new add_generic<int16_t>(num_inputs, 2*vlen));
}

add::sptr add::make_sc8_sc8(const size_t num_inputs, const size_t vlen){
    return gnuradio::get_initial_sptr(new add_generic<int8_t>(num_inputs, 2*vlen));
}

add::sptr add::make_f32_f32(const size_t num_inputs, const size_t vlen){
    return gnuradio::get_initial_sptr(new add_generic<float>(num_inputs, vlen));
}

add::sptr add::make_s32_s32(const size_t num_inputs, const size_t vlen){
    return gnuradio::get_initial_sptr(new add_generic<int32_t>(num_inputs, vlen));
}

add::sptr add::make_s16_s16(const size_t num_inputs, const size_t vlen){
    return gnuradio::get_initial_sptr(new add_generic<int16_t>(num_inputs, vlen));
}

add::sptr add::make_s8_s8(const size_t num_inputs, const size_t vlen){
    return gnuradio::get_initial_sptr(new add_generic<int8_t>(num_inputs, vlen));
}

