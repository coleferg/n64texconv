# ExoQuantPY (ExoQuant v0.7)
#
# Copyright (c) 2019 David Benepe
# Copyright (c) 2004 Dennis Ranke
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

#/******************************************************************************
#* Usage:
#* ------
#*
#* exq = ExoQuant() // init quantizer (per image)
#* exq.feed(<byte array of rgba32 data>) // feed pixel data (32bpp)
#* exq.quantize(<num of colors>) // find palette
#* rgba32Palette = exq.get_palette(<num of colors>) // get palette
#* indexData = exq.map_image(<num of pixels>, <byte array of rgba32 data>)
#* or:
#* indexData = exq.map_image_ordered(<width>, <height>, <byte array of rgba32 data>)
#* // map image to palette
#*
#* Notes:
#* ------
#*
#* All 32bpp data (input data and palette data) is considered a byte stream
#* of the format:
#* R0 G0 B0 A0 R1 G1 B1 A1 ...
#* If you want to use a different order, the easiest way to do this is to
#* change the SCALE_x constants in expquant.h, as those are the only differences
#* between the channels.
#*
#******************************************************************************/

import math
import random

_EXQ_HASH_BITS = 16
_EXQ_HASH_SIZE = 1 << _EXQ_HASH_BITS
_EXQ_SCALE_R = 1.0
_EXQ_SCALE_G = 1.2
_EXQ_SCALE_B = 0.8
_EXQ_SCALE_A = 1.0

class ExqColor:
    def __init__(self):
        self.r = 0.0
        self.g = 0.0
        self.b = 0.0
        self.a = 0.0

class ExqHistogramEntry:
    def __init__(self):
        self.color = ExqColor()
        self.ored = 0 # byte
        self.ogreen = 0 # byte
        self.oblue = 0 # byte
        self.oalpha = 0 # byte
        self.palIndex = 0 # int
        self.ditherScale = ExqColor()
        self.ditherIndex = [0] * 4 # int[4]
        self.num = 0 # int
        self.pNext = None # ExqHistogramEntry
        self.pNextInHash = None # ExqHistogramEntry

class ExqNode:
    def __init__(self):
        self.dir = ExqColor() # ExqColor
        self.avg = ExqColor() # ExqColor
        self.vdif = 0.0 # double
        self.err = 0.0 # double
        self.num = 0 # int 
        self.pHistogram = None # ExqHistogramEntry
        self.pSplit = None # ExqHistogramEntry

class ExqData:
    def __init__(self):
        self.pHash = [None] * _EXQ_HASH_SIZE # ExqHistogramEntry[_EXQ_HASH_SIZE]
        self.node = [None] * 256 # ExqNode[256]
        self.numColors = 0 # int
        self.numBitsPerChannel = 0 # int
        self.optimized = False # bool
        self.transparency = False # bool

class ExoQuant:
    def __init__(self):
        self.sortDir = ExqColor()
        self.pExq = ExqData()
        
        for i in range(256):
            self.pExq.node[i] = ExqNode()

        for i in range(_EXQ_HASH_SIZE):
            self.pExq.pHash[i] = None

        self.pExq.numColors = 0
        self.pExq.optimized = False
        self.pExq.transparency = True
        self.pExq.numBitsPerChannel = 8
    
    def no_transparency(self):
        self.pExq.transparency = False
    
    def make_hash(self, rgba):
        rgba -= (rgba >> 13) | (rgba << 19)
        rgba &= 0xFFFFFFFF
        rgba -= (rgba >> 13) | (rgba << 19)
        rgba &= 0xFFFFFFFF
        rgba -= (rgba >> 13) | (rgba << 19)
        rgba &= 0xFFFFFFFF
        rgba -= (rgba >> 13) | (rgba << 19)
        rgba &= 0xFFFFFFFF
        rgba -= (rgba >> 13) | (rgba << 19)
        rgba &= (_EXQ_HASH_SIZE - 1)
        return rgba
    
    def to_rgba(self, r, g, b, a):
        return r | (g << 8) | (b << 16) | (a << 24)
        
    def feed(self, pData):
        channelMask = 0xFF00 >> self.pExq.numBitsPerChannel
        nPixels = len(pData) // 4
        
        for i in range(nPixels):
            r = pData[i * 4 + 0]
            g = pData[i * 4 + 1] 
            b = pData[i * 4 + 2]
            a = pData[i * 4 + 3]
            hash = self.make_hash(self.to_rgba(r, g, b, a))
            pCur = self.pExq.pHash[hash]

            while (pCur != None and (pCur.ored != r or pCur.ogreen != g or pCur.oblue != b or pCur.oalpha != a)):
                pCur = pCur.pNextInHash

            if (pCur != None):
                pCur.num += 1
            else:
                pCur = ExqHistogramEntry()
                pCur.pNextInHash = self.pExq.pHash[hash]
                self.pExq.pHash[hash] = pCur
                pCur.ored = r
                pCur.ogreen = g
                pCur.oblue = b
                pCur.oalpha = a
                r &= channelMask 
                g &= channelMask 
                b &= channelMask
                pCur.color.r = r / 255.0 * _EXQ_SCALE_R
                pCur.color.g = g / 255.0 * _EXQ_SCALE_G
                pCur.color.b = b / 255.0 * _EXQ_SCALE_B
                pCur.color.a = a / 255.0 * _EXQ_SCALE_A
                if self.pExq.transparency:
                    pCur.color.r *= pCur.color.a
                    pCur.color.g *= pCur.color.a
                    pCur.color.b *= pCur.color.a
                pCur.num = 1
                pCur.palIndex = -1
                pCur.ditherScale.r = pCur.ditherScale.g = pCur.ditherScale.b = pCur.ditherScale.a = -1
                pCur.ditherIndex[0] = pCur.ditherIndex[1] = pCur.ditherIndex[2] = pCur.ditherIndex[3] = -1

    def quantize(self, nColors):
        self.quantize_ex(nColors, False)
    
    def quantize_hq(self, nColors):
        self.quantize_ex(nColors, True)

    def quantize_ex(self, nColors, hq):
        pCur = None
        pNext = None

        if (nColors > 256):
            nColors = 256

        if (self.pExq.numColors == 0):
            self.pExq.node[0].pHistogram = None
            for i in range(_EXQ_HASH_SIZE):
                pCur = self.pExq.pHash[i]
                while (pCur != None):
                    pCur.pNext = self.pExq.node[0].pHistogram
                    self.pExq.node[0].pHistogram = pCur
                    pCur = pCur.pNextInHash
            self.sum_node(self.pExq.node[0])
            self.pExq.numColors = 1
        
        for i in range(self.pExq.numColors, nColors):
            beste = 0
            besti = 0
            
            for j in range(i):
                if (self.pExq.node[j].vdif >= beste):
                    beste = self.pExq.node[j].vdif
                    besti = j
            
            pCur = self.pExq.node[besti].pHistogram

            self.pExq.node[besti].pHistogram = None
            self.pExq.node[i].pHistogram = None
            while (pCur != None and pCur != self.pExq.node[besti].pSplit):
                pNext = pCur.pNext
                pCur.pNext = self.pExq.node[i].pHistogram
                self.pExq.node[i].pHistogram = pCur
                pCur = pNext

            while (pCur != None):
                pNext = pCur.pNext
                pCur.pNext = self.pExq.node[besti].pHistogram
                self.pExq.node[besti].pHistogram = pCur
                pCur = pNext
            
            self.sum_node(self.pExq.node[besti])
            self.sum_node(self.pExq.node[i])

            self.pExq.numColors = i + 1
            if (hq):
                self.optimize_palette(1)

        self.pExq.optimized = False
    
    def get_mean_error(self):
        n = 0
        err = 0

        for i in range(self.pExq.numColors):
            n += self.pExq.node[i].num
            err += self.pExq.node[i].err

        return math.sqrt(err / n) * 256

    def get_palette(self, nColors):
        channelMask = 0xff00 >> self.pExq.numBitsPerChannel

        pPal = [0] * (nColors * 4)

        if nColors > self.pExq.numColors:
            nColors = self.pExq.numColors
        
        if not self.pExq.optimized:
            self.optimize_palette(4)
        
        for i in range(nColors):
            r = self.pExq.node[i].avg.r
            g = self.pExq.node[i].avg.g
            b = self.pExq.node[i].avg.b
            a = self.pExq.node[i].avg.a

            if self.pExq.transparency and a != 0:
                r /= a 
                g /= a 
                b /= a

            pPalIndex = i * 4
            pPal[pPalIndex + 0] = r / _EXQ_SCALE_R * 255.9
            pPal[pPalIndex + 1] = g / _EXQ_SCALE_G * 255.9
            pPal[pPalIndex + 2] = b / _EXQ_SCALE_B * 255.9
            pPal[pPalIndex + 3] = a / _EXQ_SCALE_A * 255.9
            
            for j in range(3):
                pPal[pPalIndex + j] = int(pPal[pPalIndex + j] + (1 << (8 - self.pExq.numBitsPerChannel)) // 2) & channelMask
        
        return pPal

    def set_palette(self, pPal, nColors):
        self.pExq.numColors = nColors

        for i in range(nColors):
            self.pExq.node[i].avg.r = pPal[i * 4 + 0] * _EXQ_SCALE_R / 255.9
            self.pExq.node[i].avg.g = pPal[i * 4 + 1] * _EXQ_SCALE_G / 255.9
            self.pExq.node[i].avg.b = pPal[i * 4 + 2] * _EXQ_SCALE_B / 255.9
            self.pExq.node[i].avg.a = pPal[i * 4 + 3] * _EXQ_SCALE_A / 255.9

        self.pExq.optimized = True
    
    def map_image(self, nPixels, pIn):
        c = ExqColor()
        pHist = None

        pOut = [0] * nPixels

        if not self.pExq.optimized:
            self.optimize_palette(4)

        for i in range(nPixels):
            pHist = self.find_histogram(pIn, i)
            if (pHist != None and pHist.palIndex != -1):
                pOut[i] = pHist.palIndex
            else:
                c.r = pIn[i * 4 + 0] / 255.0 * _EXQ_SCALE_R
                c.g = pIn[i * 4 + 1] / 255.0 * _EXQ_SCALE_G
                c.b = pIn[i * 4 + 2] / 255.0 * _EXQ_SCALE_B
                c.a = pIn[i * 4 + 3] / 255.0 * _EXQ_SCALE_A
                if(self.pExq.transparency):
                    c.r *= c.a 
                    c.g *= c.a 
                    c.b *= c.a
                pOut[i] = self.find_nearest_color(c)
                if(pHist != None):
                    pHist.palIndex = i
        
        return pOut

    def map_image_ordered(self, width, height, pIn):
        return self.map_image_dither(width, height, pIn, True)

    def map_image_random(self, nPixels, pIn):
        return self.map_image_dither(nPixels, 1, pIn, False)
    
    #private readonly Random random = Random()
    def map_image_dither(self, width, height, pIn, ordered):
        ditherMatrix = [ -0.375, 0.125, 0.375, -0.125 ]

        p = ExqColor() 
        scale = ExqColor()
        tmp = ExqColor()
        pHist = None
        
        pOut = [0] * (width * height)

        if not self.pExq.optimized:
            self.optimize_palette(4)

        for y in range(height):
            for x in range(width):
                index = y * width + x

                if ordered:
                    d = (x & 1) + (y & 1) * 2
                else:
                    d = randrange(32767) & 3

                pHist = self.find_histogram(pIn, index)

                p.r = pIn[index * 4 + 0] / 255.0 * _EXQ_SCALE_R
                p.g = pIn[index * 4 + 1] / 255.0 * _EXQ_SCALE_G
                p.b = pIn[index * 4 + 2] / 255.0 * _EXQ_SCALE_B
                p.a = pIn[index * 4 + 3] / 255.0 * _EXQ_SCALE_A

                if self.pExq.transparency:
                    p.r *= p.a 
                    p.g *= p.a 
                    p.b *= p.a

                if pHist == None or pHist.ditherScale.r < 0:
                    i = self.find_nearest_color(p)
                    scale.r = self.pExq.node[i].avg.r - p.r
                    scale.g = self.pExq.node[i].avg.g - p.g
                    scale.b = self.pExq.node[i].avg.b - p.b
                    scale.a = self.pExq.node[i].avg.a - p.a
                    tmp.r = p.r - scale.r / 3
                    tmp.g = p.g - scale.g / 3
                    tmp.b = p.b - scale.b / 3
                    tmp.a = p.a - scale.a / 3
                    j = self.find_nearest_color(tmp)
                    if i == j:
                        tmp.r = p.r - scale.r * 3
                        tmp.g = p.g - scale.g * 3
                        tmp.b = p.b - scale.b * 3
                        tmp.a = p.a - scale.a * 3
                        j = self.find_nearest_color(tmp)
                    if i != j:
                        scale.r = (self.pExq.node[j].avg.r - self.pExq.node[i].avg.r) * 0.8
                        scale.g = (self.pExq.node[j].avg.g - self.pExq.node[i].avg.g) * 0.8
                        scale.b = (self.pExq.node[j].avg.b - self.pExq.node[i].avg.b) * 0.8
                        scale.a = (self.pExq.node[j].avg.a - self.pExq.node[i].avg.a) * 0.8
                        if scale.r < 0: 
                            scale.r = -scale.r
                        if scale.g < 0: 
                            scale.g = -scale.g
                        if scale.b < 0: 
                            scale.b = -scale.b
                        if scale.a < 0: 
                            scale.a = -scale.a
                    else:
                        scale.r = scale.g = scale.b = scale.a = 0

                    if pHist != None:
                        pHist.ditherScale.r = scale.r
                        pHist.ditherScale.g = scale.g
                        pHist.ditherScale.b = scale.b
                        pHist.ditherScale.a = scale.a
                else:
                    scale.r = pHist.ditherScale.r
                    scale.g = pHist.ditherScale.g
                    scale.b = pHist.ditherScale.b
                    scale.a = pHist.ditherScale.a

                if (pHist != None and pHist.ditherIndex[d] >= 0):
                    pOut[index] = pHist.ditherIndex[d]
                else:
                    tmp.r = p.r + scale.r * ditherMatrix[d]
                    tmp.g = p.g + scale.g * ditherMatrix[d]
                    tmp.b = p.b + scale.b * ditherMatrix[d]
                    tmp.a = p.a + scale.a * ditherMatrix[d]
                    pOut[index] = self.find_nearest_color(tmp)
                    if pHist != None:
                        pHist.ditherIndex[d] = pOut[index]
            
        return pOut
    
    def sum_node(self, pNode):
        n = 0
        fsum = ExqColor()
        fsum2 = ExqColor()
        vc = ExqColor() 
        tmp = ExqColor() 
        tmp2 = ExqColor() 
        sum = ExqColor() 
        sum2 = ExqColor()
        pCur = None

        fsum.r = fsum.g = fsum.b = fsum.a = 0
        fsum2.r = fsum2.g = fsum2.b = fsum2.a = 0

        pCur = pNode.pHistogram
        while pCur != None:
            n += pCur.num
            fsum.r += pCur.color.r * pCur.num
            fsum.g += pCur.color.g * pCur.num
            fsum.b += pCur.color.b * pCur.num
            fsum.a += pCur.color.a * pCur.num
            fsum2.r += pCur.color.r * pCur.color.r * pCur.num
            fsum2.g += pCur.color.g * pCur.color.g * pCur.num
            fsum2.b += pCur.color.b * pCur.color.b * pCur.num
            fsum2.a += pCur.color.a * pCur.color.a * pCur.num
            pCur = pCur.pNext
            
        pNode.num = n
        if n == 0:
            pNode.vdif = 0
            pNode.err = 0
            return

        pNode.avg.r = fsum.r / n
        pNode.avg.g = fsum.g / n
        pNode.avg.b = fsum.b / n
        pNode.avg.a = fsum.a / n
        
        vc.r = fsum2.r - fsum.r * pNode.avg.r
        vc.g = fsum2.g - fsum.g * pNode.avg.g
        vc.b = fsum2.b - fsum.b * pNode.avg.b
        vc.a = fsum2.a - fsum.a * pNode.avg.a
        
        v = vc.r + vc.g + vc.b + vc.a
        pNode.err = v
        pNode.vdif = -v
        
        if vc.r > vc.g and vc.r > vc.b and vc.r > vc.a:
            pNode.pHistogram = self.sort(pNode.pHistogram, self.sort_by_red)
        elif vc.g > vc.b and vc.g > vc.a:
            pNode.pHistogram = self.sort(pNode.pHistogram, self.sort_by_green)
        elif vc.b > vc.a:
            pNode.pHistogram = self.sort(pNode.pHistogram, self.sort_by_blue)
        else:
            pNode.pHistogram = self.sort(pNode.pHistogram, self.sort_by_alpha)
            
        pNode.dir.r = pNode.dir.g = pNode.dir.b = pNode.dir.a = 0
        pCur = pNode.pHistogram
        while pCur != None:
            tmp.r = (pCur.color.r - pNode.avg.r) * pCur.num
            tmp.g = (pCur.color.g - pNode.avg.g) * pCur.num
            tmp.b = (pCur.color.b - pNode.avg.b) * pCur.num
            tmp.a = (pCur.color.a - pNode.avg.a) * pCur.num
            if tmp.r * pNode.dir.r + tmp.g * pNode.dir.g + tmp.b * pNode.dir.b + tmp.a * pNode.dir.a < 0:
                tmp.r = -tmp.r
                tmp.g = -tmp.g
                tmp.b = -tmp.b
                tmp.a = -tmp.a
            pNode.dir.r += tmp.r
            pNode.dir.g += tmp.g
            pNode.dir.b += tmp.b
            pNode.dir.a += tmp.a
            pCur = pCur.pNext
        
        try:
            isqrt = 1 / math.sqrt(pNode.dir.r * pNode.dir.r + pNode.dir.g * pNode.dir.g + pNode.dir.b * pNode.dir.b + pNode.dir.a * pNode.dir.a)
        except ZeroDivisionError:
            isqrt = float('Inf')
        
        pNode.dir.r *= isqrt
        pNode.dir.g *= isqrt
        pNode.dir.b *= isqrt
        pNode.dir.a *= isqrt

        self.sortDir = pNode.dir
        pNode.pHistogram = self.sort(pNode.pHistogram, self.sort_by_dir)

        sum.r = sum.g = sum.b = sum.a = 0
        sum2.r = sum2.g = sum2.b = sum2.a = 0
        n2 = 0
        pNode.pSplit = pNode.pHistogram
        pCur = pNode.pHistogram 
        while pCur != None:
            if pNode.pSplit == None:
                pNode.pSplit = pCur

            n2 += pCur.num
            sum.r += pCur.color.r * pCur.num
            sum.g += pCur.color.g * pCur.num
            sum.b += pCur.color.b * pCur.num
            sum.a += pCur.color.a * pCur.num
            sum2.r += pCur.color.r * pCur.color.r * pCur.num
            sum2.g += pCur.color.g * pCur.color.g * pCur.num
            sum2.b += pCur.color.b * pCur.color.b * pCur.num
            sum2.a += pCur.color.a * pCur.color.a * pCur.num
            if n == n2:
                break
            tmp.r = sum2.r - sum.r * sum.r / n2
            tmp.g = sum2.g - sum.g * sum.g / n2
            tmp.b = sum2.b - sum.b * sum.b / n2
            tmp.a = sum2.a - sum.a * sum.a / n2
            tmp2.r = (fsum2.r - sum2.r) - (fsum.r - sum.r) * (fsum.r - sum.r) / (n - n2)
            tmp2.g = (fsum2.g - sum2.g) - (fsum.g - sum.g) * (fsum.g - sum.g) / (n - n2)
            tmp2.b = (fsum2.b - sum2.b) - (fsum.b - sum.b) * (fsum.b - sum.b) / (n - n2)
            tmp2.a = (fsum2.a - sum2.a) - (fsum.a - sum.a) * (fsum.a - sum.a) / (n - n2)

            nv = tmp.r + tmp.g + tmp.b + tmp.a + tmp2.r + tmp2.g + tmp2.b + tmp2.a
            if -nv > pNode.vdif:
                pNode.vdif = -nv
                pNode.pSplit = None
            pCur = pCur.pNext

        if pNode.pSplit == pNode.pHistogram:
            pNode.pSplit = pNode.pSplit.pNext

        pNode.vdif += v

    def optimize_palette(self, iter):
        pCur = None

        self.pExq.optimized = True

        for n in range(iter):
            for i in range(self.pExq.numColors):
                self.pExq.node[i].pHistogram = None
            for i in range(_EXQ_HASH_SIZE):
                pCur = self.pExq.pHash[i]
                while pCur != None:
                    j = self.find_nearest_color(pCur.color)
                    pCur.pNext = self.pExq.node[j].pHistogram
                    self.pExq.node[j].pHistogram = pCur
                    pCur = pCur.pNextInHash
            for i in range(self.pExq.numColors):
                self.sum_node(self.pExq.node[i])

    def find_nearest_color(self, pColor):
        dif = ExqColor()
        bestv = 16
        besti = 0

        for i in range(self.pExq.numColors):
            dif.r = pColor.r - self.pExq.node[i].avg.r
            dif.g = pColor.g - self.pExq.node[i].avg.g
            dif.b = pColor.b - self.pExq.node[i].avg.b
            dif.a = pColor.a - self.pExq.node[i].avg.a
            if (dif.r * dif.r + dif.g * dif.g + dif.b * dif.b + dif.a * dif.a < bestv):
                bestv = dif.r * dif.r + dif.g * dif.g + dif.b * dif.b + dif.a * dif.a
                besti = i
        return besti
    
    def find_histogram(self, pCol, index):
        pCur = None
        
        r = pCol[index * 4 + 0]
        g = pCol[index * 4 + 1]
        b = pCol[index * 4 + 2]
        a = pCol[index * 4 + 3]
        
        hash = self.make_hash(self.to_rgba(r, g, b, a))
        
        pCur = self.pExq.pHash[hash]
        while pCur != None and (pCur.ored != r or pCur.ogreen != g or pCur.oblue != b or pCur.oalpha != a):
            pCur = pCur.pNextInHash

        return pCur

    def sort(self, ppHist, sortfunc):
        pLow = None
        pHigh = None
        pCur = None
        pNext = None
        n = 0
        sum = 0

        pCur = ppHist
        while pCur != None:
            n += 1
            sum += sortfunc(pCur)
            pCur = pCur.pNext
        
        if n < 2:
            return ppHist

        sum /= n

        pLow = pHigh = None
        pCur = ppHist
        while pCur != None:
            pNext = pCur.pNext
            if sortfunc(pCur) < sum:
                pCur.pNext = pLow
                pLow = pCur
            else:
                pCur.pNext = pHigh
                pHigh = pCur
            pCur = pNext

        if pLow == None:
            ppHist = pHigh
            return ppHist
        if pHigh == None:
            ppHist = pLow
            return ppHist

        pLow = self.sort(pLow, sortfunc)
        pHigh = self.sort(pHigh, sortfunc)

        ppHist = pLow
        while pLow.pNext != None:
            pLow = pLow.pNext

        pLow.pNext = pHigh
        
        return ppHist

    def sort_by_red(self, pHist):
        return pHist.color.r

    def sort_by_green(self, pHist):
        return pHist.color.g

    def sort_by_blue(self, pHist):
        return pHist.color.b

    def sort_by_alpha(self, pHist):
        return pHist.color.a

    def sort_by_dir(self, pHist):
        return pHist.color.r * self.sortDir.r + pHist.color.g * self.sortDir.g + pHist.color.b * self.sortDir.b + pHist.color.a * self.sortDir.a
        