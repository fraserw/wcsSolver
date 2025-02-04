#! /usr/bin/env pythonw

import astropy.io.fits as fits
from astropy import wcs as WCS
import numpy as np
from numpy import linalg
from trippy import scamp
from os import path
import os, sys
import pylab as pyl
from astropy.visualization import interval
import numdisplay
from matplotlib.patches import Circle
from matplotlib import gridspec


#sextractor shape cut  -- done
#window size command line option -- done
#zoom on sources -- done
#Bayes information criterion -- is now printed
#parameters into the headers
#instructions


def trimCatalog(cat, minBA=0.85, maxMagDiff = 0.5):

    good=[]
    for i in range(len(cat['XWIN_IMAGE'])):
        try:
            ba = cat['BWIN_IMAGE'][i]/cat['AWIN_IMAGE'][i]
            m = cat['MAG_AUTO'][i]
            ma = cat['MAG_APER'][i]
            flag = cat['FLAGS'][i]
        except:
            pass
        #if cat['FLAGS'][i]==0 and m>0 and m<26:
        if m>0 and m<26 and flag == 0 and ba>minBA and abs(ma-m)<maxMagDiff:
            good.append(i)
    good = np.array(good)

    #(X,Y,A,B) = (cat['XWIN_IMAGE'][good],cat['YWIN_IMAGE'][good],cat['AWIN_IMAGE'][good],cat['BWIN_IMAGE'][good])
    #w = np.where(B/A>minBA)
    #good = good[w]

    outcat = {}
    for i in cat:
        outcat[i] = cat[i][good]
    #w = np.where((outcat['MAG_AUTO'] - outcat['MAG_APER'])<0.2)
    #for i in range(len(outcat['XWIN_IMAGE'])):
    #    print outcat['XWIN_IMAGE'][i],outcat['YWIN_IMAGE'][i],outcat['MAG_AUTO'][i]-outcat['MAG_APER'][i]

    return outcat


d2r= np.pi/180.0

class matrixWCSSolver(object):

    def __init__(self, imagedata, header, imageSources, refSources, xo = 512.0, yo = 512.0, windowSize = 13):

        if 'B_DEC_7' in header:
            self.b_ra = []
            self.b_dec = []
            for i in range(8):
                self.b_ra.append(header['B_RA_{}'.format(i)])
                self.b_dec.append(header['B_DEC_{}'.format(i)])
            self.b_ra = np.array(self.b_ra)
            self.b_dec = np.array(self.b_dec)
        if 'B_DEC_L5' in header:
            self.b_ra_low = []
            self.b_dec_low = []
            for i in range(6):
                self.b_ra_low.append(header['B_RA_L{}'.format(i)])
                self.b_dec_low.append(header['B_DEC_L{}'.format(i)])
            self.b_ra_low = np.array(self.b_ra_low)
            self.b_dec_low = np.array(self.b_dec_low)


        self.imageSources = imageSources
        self.refSources = refSources
        self._xo = xo
        self._yo = yo
        self.header = header
        self.header.set('RADESYSa','FK5')
        self.imagedata = np.copy(imagedata)

        #scratch crap pixel value fix
        mean = np.median(self.imagedata[::3,::3])
        w = np.where(self.imagedata<0)
        self.imagedata[w] = mean

        (self._z1,self._z2) = numdisplay.zscale.zscale(self.imagedata, contrast = 0.4)
        self._normer = interval.ManualInterval(self._z1,self._z2)

        self._wcs  = WCS.WCS(header)
        if self.refSources is not None:
            self._refSourcePix = self._wcs.wcs_world2pix(self.refSources[:,:2],0)

            (a,b) = self.imagedata.shape
            w = np.where((self._refSourcePix[:,0]>-100)&(self._refSourcePix[:,0]<b+100)&(self._refSourcePix[:,1]>-100)&(self._refSourcePix[:,1]<a+100))
            self._refSourcePix = self._refSourcePix[w]
            self.refSources = self.refSources[w]

        self._initSourceSelection = None
        self._initRefSelection = None
        self.matches = []

        self.windowSize = windowSize
        self._lastKilled = []


    def initialMatch(self, maxDeltaMag = 1.5):
        fig = pyl.figure('Full Image', figsize = (self.windowSize, self.windowSize))
        sp = fig.add_subplot(111)
        implot = pyl.imshow(self._normer(self.imagedata))
        implot.set_cmap('hot')
        #plot the catalog sources
        pyl.scatter(self._refSourcePix[:,0], self._refSourcePix[:,1], c = 'g', s = 15)
        #pyl.scatter(self.imageSources[:,0]-1, self.imageSources[:,1]-1,c='b',alpha = 0.5)


        #plot the actual on image sources
        self.circles = []
        for i in range(len(self.imageSources)):
            circle=Circle(self.imageSources[i,:2]-np.ones(2),20,facecolor="none",edgecolor='b',linestyle='dashed',linewidth=2, alpha=0.75,zorder=10)
            sp.add_patch(circle)
            self.circles.append(circle)
        sp.invert_yaxis()
        sp.set_xlim(0,self.imagedata.shape[1])
        sp.set_ylim(0,self.imagedata.shape[1])

        pyl.connect('button_press_event',self._getStar)

        pyl.show()

    def _getStar(self, event, maxDist =  10, maxMagDiff = 1.0):
        if event.button==1:
            rcx = event.xdata
            rcy = event.ydata
            if rcx==None or rcy==None: return

            distToImageSource = ((self.imageSources[:,0] - (rcx + 1))**2 + (self.imageSources[:,1] - (rcy + 1))**2)**0.5
            argMin = np.argmin(distToImageSource)
            minDist = distToImageSource[argMin]

            self._initSourceSelection = self.imageSources[argMin]
            (x,y,m) = self._initSourceSelection[:3]
            print '   Selected image source at {:.3f}, {:.3f} with magnitude {:.2f}.'.format(x,y,m)

        elif event.button==3:
            rcx = event.xdata
            rcy = event.ydata
            if rcx==None or rcy==None: return

            distToImageSource = ((self._refSourcePix[:,0] - (rcx + 1))**2 + (self._refSourcePix[:,1] - (rcy + 1))**2)**0.5
            argMin = np.argmin(distToImageSource)
            minDist = distToImageSource[argMin]

            self._initRefSelection = argMin
            (x,y) = self._refSourcePix[argMin]
            (ra,dec,r,g) = self.refSources[argMin,:4]
            print '   Selected reference star at {:.3f}, {:.3f} with magnitudes r={:.2f} g={:.2f}.'.format(x,y,r,g)

        if self._initRefSelection is not None and self._initSourceSelection is not None:

            self.matches = []

            off_x = self._initSourceSelection[0] - self._refSourcePix[self._initRefSelection,0]
            off_y = self._initSourceSelection[1] - self._refSourcePix[self._initRefSelection,1]

            deltaMags = []
            for i in range(len(self.refSources)):
                (ox,oy) = self._refSourcePix[i,:2] - np.ones(2)
                (nx,ny) = (ox + off_x, oy + off_y)

                dist = ((nx - self.imageSources[:,0])**2 + (ny - self.imageSources[:,1])**2)**0.5
                argMin = np.argmin(dist)
                if dist[argMin] < maxDist:
                    deltaMags.append(self.refSources[i,2]-self.imageSources[argMin,2])

            deltaMags = np.array(deltaMags)
            correctedMags = self.imageSources[:,2] + np.median(deltaMags)


            for i in range(len(self.refSources)):
                (ox,oy) = self._refSourcePix[i,:2] - np.ones(2)
                (nx,ny) = (ox + off_x, oy + off_y)

                dist = ((nx - self.imageSources[:,0])**2 + (ny - self.imageSources[:,1])**2)**0.5
                argMin = np.argmin(dist)
                if dist[argMin] < maxDist and (correctedMags[argMin] - self.refSources[i,2])<maxMagDiff:

                    pyl.plot([ox,nx], [oy,ny], 'b-', lw=3)

                    self.matches.append([self.refSources[i,0], self.refSources[i,1],self.imageSources[argMin,0], self.imageSources[argMin,1],self.imageSources[argMin,4],self.imageSources[argMin,5]])
            self.matches = np.array(self.matches)
            pyl.draw()

    def _resid4Panel(self):
        fig = pyl.figure(' Fourpanel', figsize = (self.windowSize*2.0, self.windowSize))
        self.gs = gridspec.GridSpec(2,3)
        self.gs.update(wspace = 0.0, hspace = 0.0)
        self._sp1 = pyl.subplot(self.gs[0,0],xticklabels = '')
        self._sp2 = pyl.subplot(self.gs[0,1],xticklabels = '',yticklabels = '')
        self._sp3 = pyl.subplot(self.gs[1,0])
        self._sp4 = pyl.subplot(self.gs[1,1],yticklabels = '')

        self.gs2 = gridspec.GridSpec(2,3)
        self.gs2.update(hspace = 0.0)
        self._sp5 = pyl.subplot(self.gs2[0,2])
        self._sp6 = pyl.subplot(self.gs2[1,2])
        """
        fig.subplots_adjust(hspace = 0, wspace = 0)
        self._sp1 = fig.add_subplot(221,xticklabels = '')
        self._sp2 = fig.add_subplot(222,xticklabels = '',yticklabels = '')
        self._sp3 = fig.add_subplot(223)
        self._sp4 = fig.add_subplot(224,yticklabels = '')
        """

        self.dra = (self.RA - self.pra)*3600.0
        self.ddec = (self.DEC - self.pdec)*3600.0
        self.dra_low = (self.RA - self.pra_low)*3600.0
        self.ddec_low = (self.DEC - self.pdec_low)*3600.0

        self._sp1.scatter(self.X,self.dra, s = 40)
        self._sp3.scatter(self.X,self.ddec, s = 40)
        self._sp2.scatter(self.Y,self.dra, s = 40)
        self._sp4.scatter(self.Y,self.ddec, s = 40)

        self._sp5.plot(np.arange(len(self._killList[:,2])), np.abs(self._killList[:,4]), 'b-o', lw=2, label = 'RA')
        self._sp5.plot(np.arange(len(self._killList[:,2])), np.abs(self._killList[:,5]), 'r-o', lw=2, label = 'Dec')
        self._sp5.plot([len(self._lastKilled), len(self._lastKilled)], [0.0,np.nanmax(np.abs(self._killList[:,4]))], 'k--')
        self._sp5.set_xlim(-0.05,len(self._killList[:,2])+1)
        self._sp5.legend()

        self.twin = self._sp5.twiny()
        self.twin.set_xlim(len(self.goodMatches), len(self.goodMatches)-len(self._killList[:,2])-1)
        self.twin.set_xlabel('Number Match Stars')
        self.twin.plot([12,12], [self.twin.get_ylim()[0],self.twin.get_ylim()[1]], 'r:', lw=3)


        self._sp6.plot(np.arange(len(self._killList[:,2])), np.abs(self._killList[:,2]), 'b-o', lw=2, label = 'RA')
        self._sp6.plot(np.arange(len(self._killList[:,2])), np.abs(self._killList[:,3]), 'r-o', lw=2, label = 'Dec')
        self._sp6.plot([len(self._lastKilled), len(self._lastKilled)], [0.0,np.nanmax(np.abs(self._killList[:,2]))], 'k--')
        self._sp6.plot([-0.05,len(self._killList[:,2])+1],[3.0,3.0],'r-',lw=3)
        self._sp6.set_xlim(-0.05,len(self._killList[:,2])+1)
        self._sp6.legend()


        self._sp4.set_xlabel('Y')
        self._sp3.set_xlabel('X')
        self._sp3.set_ylabel('delta Dec (")')
        self._sp1.set_ylabel('delta RA (")')

        self._sp5.set_ylabel('Killed Star Residual (")')
        self._sp6.set_ylabel('Max delta/Sample deviation')
        self._sp6.set_xlabel('Kill Number')


        w = np.where(self.goodMatches)
        self._sp1.set_title('{:.3f}/{:.3f}"'.format(np.std(self.dra[w]),np.std(self.dra_low[w])))
        self._sp2.set_title('{:.3f}/{:.3f}"'.format(np.std(self.ddec[w]),np.std(self.ddec_low[w])))

        pyl.connect('button_press_event', self._killResid)
        pyl.connect('key_press_event', self._zoomResid)

        self._fullZooms = [self._sp1.get_xlim(),self._sp1.get_ylim(), self._sp2.get_xlim(),self._sp2.get_ylim(), self._sp3.get_xlim(),self._sp3.get_ylim(), self._sp4.get_xlim(),self._sp4.get_ylim()]
        self._zoomed = False
        pyl.show()

    def _zoomResid(self, event):

        if event.key in ['z','Z'] or event.key in ['r','R']:
            if not self._zoomed and event.key in ['z','Z']:
                w = np.where(self.goodMatches)

                x_min = np.min(self.X[w])
                x_max = np.max(self.X[w])
                y_min = np.min(self.Y[w])
                y_max = np.max(self.Y[w])
                r_min = np.min(self.dra[w])-0.005
                r_max = np.max(self.dra[w])+0.005
                d_min = np.min(self.ddec[w])-0.005
                d_max = np.max(self.ddec[w])+0.005

                self._zoomed = True
            else:
                (r_min,r_max) = self._fullZooms[1]
                (d_min,d_max) = self._fullZooms[3]

                self._zoomed = False

            self._sp1.set_ylim(r_min, r_max)
            self._sp2.set_ylim(r_min, r_max)
            self._sp3.set_ylim(d_min, d_max)
            self._sp4.set_ylim(d_min, d_max)

            pyl.draw()

        if event.key in ['r', 'R']:
            self.goodMatches *= 0
            self.goodMatches += 1
            self._lastKilled = []
            self._fullRedraw()

        elif event.key in ['k','K']:
            toKill = self._whichToKill()[0]

            self._lastKilled.append(toKill)
            self.goodMatches[toKill] = 0
            self._fullRedraw()

        elif event.key in ['j','J'] and len(self._lastKilled) > 0:
            if self.goodMatches[self._lastKilled[-1]] == 0:
                self.goodMatches[self._lastKilled[-1]] = 1
            self._lastKilled = self._lastKilled[:-1]
            self._fullRedraw()

        elif event.key == '?':
            print 'HELP!!!'
            print 'Closing the window will accept the current fit as is.'
            print
            print " -press z to zoom in on the selected good stars or out to all"
            print " -press r to reset all stars back to good and try again"
            print " -press k to kill the most discrepant point"
            print " -press j to restore the most recent point you nuked with k"
            print " -press ? to see this message"

    def _whichToKill(self):
        #get original state
        w = np.where(self.goodMatches)
        (A, b_ra, b_ra_low, b_dec_low, b_dec, predRA, predDEC, predRA_low, predDEC_low, lnL_RA, lnL_DEC, BICS) = self._solveMatrix()
        if self.useLowOrder:
            std_ra = np.std(predRA_low[w] - self.RA[w])*3600.0
            std_dec = np.std(predDEC_low[w] - self.DEC[w])*3600.0
            delta = (std_ra**2 + std_dec**2)**0.5

            #now determine which is the best to eliminate
            k_deltas = []
            individual_deltas = []
            for i in w[0]:
                self.goodMatches[i] = 0

                fake_w = np.where(self.goodMatches)
                (A, b_ra, b_dec, b_ra_low, b_dec_low, predRA, predDEC, predRA_low, predDEC_low, lnL_RA, lnL_DEC, BICS) = self._solveMatrix()
                k_std_ra = np.std(predRA_low[fake_w] - self.RA[fake_w])*3600.0
                k_std_dec = np.std(predDEC_low[fake_w] - self.DEC[fake_w])*3600.0

                k_delta = (k_std_ra**2 + k_std_dec**2)**0.5
                k_deltas.append([k_delta,
                                 (np.max(np.abs(predRA_low[fake_w] - self.RA[fake_w]))*3600.0)/k_std_ra,
                                 (np.max(np.abs(predDEC_low[fake_w] - self.DEC[fake_w]))*3600.0)/k_std_dec])

                self.goodMatches[i] = 1

            k_deltas = np.array(k_deltas)
            argmin = np.argmin(k_deltas[:,0])
            kill = w[0][argmin]

            #got which one to kill, now determine how bad that point is after killing it
            self.goodMatches[kill] = 0
            fake_w = np.where(self.goodMatches)
            (A, b_ra, b_dec, b_ra_low, b_dec_low, predRA, predDEC, predRA_low, predDEC_low, lnL_RA, lnL_DEC, BICS) = self._solveMatrix()
            idra = (predRA_low[kill] - self.RA[kill])*3600.0
            iddec = (predDEC_low[kill] - self.DEC[kill])*3600.0

        else:
            std_ra = np.std(predRA[w] - self.RA[w])*3600.0
            std_dec = np.std(predDEC[w] - self.DEC[w])*3600.0
            delta = (std_ra**2 + std_dec**2)**0.5

            #now determine which is the best to eliminate
            k_deltas = []
            individual_deltas = []
            for i in w[0]:
                self.goodMatches[i] = 0

                fake_w = np.where(self.goodMatches)
                (A, b_ra, b_dec, b_ra_low, b_dec_low, predRA, predDEC, predRA_low, predDEC_low, lnL_RA, lnL_DEC, BICS) = self._solveMatrix()
                k_std_ra = np.std(predRA[fake_w] - self.RA[fake_w])*3600.0
                k_std_dec = np.std(predDEC[fake_w] - self.DEC[fake_w])*3600.0

                k_delta = (k_std_ra**2 + k_std_dec**2)**0.5
                k_deltas.append([k_delta,
                                 (np.max(np.abs(predRA[fake_w] - self.RA[fake_w]))*3600.0)/k_std_ra,
                                 (np.max(np.abs(predDEC[fake_w] - self.DEC[fake_w]))*3600.0)/k_std_dec])

                self.goodMatches[i] = 1

            k_deltas = np.array(k_deltas)
            argmin = np.argmin(k_deltas[:,0])
            kill = w[0][argmin]

            #got which one to kill, now determine how bad that point is after killing it
            self.goodMatches[kill] = 0
            fake_w = np.where(self.goodMatches)
            (A, b_ra, b_dec, b_ra_low, b_dec_low, predRA, predDEC, predRA_low, predDEC_low, lnL_RA, lnL_DEC, BICS) = self._solveMatrix()
            idra = (predRA[kill] - self.RA[kill])*3600.0
            iddec = (predDEC[kill] - self.DEC[kill])*3600.0

        return (kill, k_deltas[argmin][0], k_deltas[argmin][1], k_deltas[argmin][2], idra,iddec)
        #self._lastKilled.append(w[0][argmin])
        #self.goodMatches[w[0][argmin]] = 0


    def _orderToKill(self):
        """
        This calls _whichToKill successively to generate an order of sources to kill
        for subplot5
        """
        #assume we do this right from the start
        self.goodMatches *= 0
        self.goodMatches += 1

        #get the max_delts for no kills
        fake_w = np.where(self.goodMatches)
        (A, b_ra, b_dec, b_ra_low, b_dec_low, predRA, predDEC, predRA_low, predDEC_low, lnL_RA, lnL_DEC, BICS) = self._solveMatrix()
        k_std_ra = np.std(predRA[fake_w] - self.RA[fake_w])*3600.0
        k_std_dec = np.std(predDEC[fake_w] - self.DEC[fake_w])*3600.0
        killList = [[-1, -32768.0, np.max(np.abs(predRA[fake_w] - self.RA[fake_w]))*3600.0/k_std_ra, np.max(np.abs(predDEC[fake_w] - self.DEC[fake_w]))*3600.0/k_std_dec , np.nan, np.nan]]
        while np.sum(self.goodMatches) > 8:
            (k, delta, max_delt_ra, max_delt_dec, idra, iddec) = self._whichToKill()
            killList.append([k,delta, max_delt_ra, max_delt_dec, idra, iddec])
            self.goodMatches[k] = 0
        self._killList = np.array(killList)

        self.goodMatches *= 0
        self.goodMatches += 1


    def _fullRedraw(self):
        (A, b_ra, b_dec, b_ra_low, b_dec_low, predRA, predDEC, predRA_low, predDEC_low, lnL_RA, lnL_DEC, BICS) = self._solveMatrix()


        self.pra = np.copy(predRA)
        self.pdec = np.copy(predDEC)
        self.pra_low = np.copy(predRA_low)
        self.pdec_low = np.copy(predDEC_low)
        self.dra = (self.RA - self.pra)*3600.0
        self.ddec = (self.DEC - self.pdec)*3600.0
        self.dra_low = (self.RA - self.pra_low)*3600.0
        self.ddec_low = (self.DEC - self.pdec_low)*3600.0
        self.b_ra = b_ra[:]
        self.b_dec = b_dec[:]
        self.b_ra_low = b_ra_low[:]
        self.b_dec_low = b_dec_low[:]

        self.lnL_RA = lnL_RA
        self.lnL_DEC = lnL_DEC
        self.BIC_RA = BICS[0]
        self.BIC_DEC = BICS[1]
        self.BIC_RA_low = BICS[2]
        self.BIC_DEC_low = BICS[3]

        self._sp1.cla()
        self._sp2.cla()
        self._sp3.cla()
        self._sp4.cla()
        self._sp5.cla()
        self._sp6.cla()

        colours = []
        for i in range(len(self.goodMatches)):
            if self.goodMatches[i]:
                colours.append('b')
            else:
                colours.append('r')
        self._sp1.scatter(self.X,self.dra,c=colours, s = 40)
        self._sp2.scatter(self.Y,self.dra,c=colours, s = 40)
        self._sp3.scatter(self.X,self.ddec,c=colours, s = 40)
        self._sp4.scatter(self.Y,self.ddec,c=colours, s = 40)

        self._sp5.plot(np.arange(len(self._killList[:,2])), np.abs(self._killList[:,4]), 'b-o', lw=2, label = 'RA')
        self._sp5.plot(np.arange(len(self._killList[:,2])), np.abs(self._killList[:,5]), 'r-o', lw=2, label = 'Dec')
        self._sp5.plot([len(self._lastKilled), len(self._lastKilled)], [0.0,np.nanmax(np.abs(self._killList[:,4]))], 'k--')
        self._sp5.set_xlim(-0.05,len(self._killList[:,2])+1)
        self._sp5.legend()

        self.twin = self._sp5.twiny()
        self.twin.set_xlim(len(self.goodMatches), len(self.goodMatches)-len(self._killList[:,2])-1)
        self.twin.set_xlabel('Number Match Stars')
        self.twin.plot([12,12], [self.twin.get_ylim()[0],self.twin.get_ylim()[1]], 'r:', lw=3)

        self._sp6.plot(np.arange(len(self._killList[:,2])), np.abs(self._killList[:,2]), 'b-o', lw=2, label = 'RA')
        self._sp6.plot(np.arange(len(self._killList[:,2])), np.abs(self._killList[:,3]), 'r-o', lw=2, label = 'Dec')
        self._sp6.plot([len(self._lastKilled), len(self._lastKilled)], [0.0,np.nanmax(np.abs(self._killList[:,2]))], 'k--')
        self._sp6.plot([-0.05,len(self._killList[:,2])+1],[3.0,3.0],'r:',lw=3)
        self._sp6.set_xlim(-0.05,len(self._killList[:,2])+1)
        self._sp6.legend()


        self._sp4.set_xlabel('Y')
        self._sp3.set_xlabel('X')
        self._sp3.set_ylabel('delta Dec (")')
        self._sp1.set_ylabel('delta RA (")')

        self._sp5.set_ylabel('Killed Star Residual (")')
        self._sp6.set_ylabel('Max delta/Sample deviation')
        self._sp6.set_xlabel('Kill Number')

        w = np.where(self.goodMatches)
        self.std_ra = np.std(self.dra[w])
        self.std_dec = np.std(self.ddec[w])
        self.std_ra_low = np.std(self.dra_low[w])
        self.std_dec_low = np.std(self.ddec_low[w])
        self._sp1.set_title('RA residuals {:.3f}/{:.3f}"'.format(self.std_ra,self.std_ra_low))
        self._sp2.set_title('Dec residuals {:.3f}/{:.3f}"'.format(self.std_dec,self.std_dec_low))

        self._fullZooms = [self._sp1.get_xlim(),self._sp1.get_ylim(), self._sp2.get_xlim(),self._sp2.get_ylim(), self._sp3.get_xlim(),self._sp3.get_ylim(), self._sp4.get_xlim(),self._sp4.get_ylim()]
        self._zoomed = False

        pyl.draw()



    def _killResid(self,event):
        rcx = event.xdata
        rcy = event.ydata
        if rcx==None or rcy==None: return

        if event.inaxes == self._sp1:
            dist = ((rcx - self.X)**2 + (rcy - self.dra)**2)**0.5
        elif event.inaxes == self._sp2:
            dist = ((rcx - self.Y)**2 + (rcy - self.dra)**2)**0.5
        elif event.inaxes == self._sp3:
            dist = ((rcx - self.X)**2 + (rcy - self.ddec)**2)**0.5
        elif event.inaxes == self._sp4:
            dist = ((rcx - self.Y)**2 + (rcy - self.ddec)**2)**0.5

        arg = np.argmin(dist)

        if event.button == 1:
            self.goodMatches[arg] = 0
        elif event.button == 3:
            self.goodMatches[arg] = 1

            if arg in self._lastKilled:
                del self._lastKilled[self._lastKilled.index(arg)]

        self._fullRedraw()



    def solveMatrix(self, useLowOrder = False):
        self.useLowOrder = useLowOrder
        if self.matches == []:
            print 'Must run _getStar first!'
            return
        self.X = self.matches[:,2] - self._xo
        self.Y = self.matches[:,3] - self._yo
        self.RA = self.matches[:,0]
        self.DEC = self.matches[:,1]
        self.dX2 = self.matches[:,4]
        self.dY2 = self.matches[:,5]




        self.goodMatches = np.ones(len(self.matches))

        (A, b_ra, b_dec, b_ra_low, b_dec_low, predRA, predDEC, predRA_low, predDEC_low, lnL_RA, lnL_DEC, BICS) = self._solveMatrix()

        self.pra = np.copy(predRA)
        self.pdec = np.copy(predDEC)
        self.pra_low = np.copy(predRA_low)
        self.pdec_low = np.copy(predDEC_low)
        self.dra = (self.RA - self.pra)*3600.0
        self.ddec = (self.DEC - self.pdec)*3600.0
        self.dra_low = (self.RA - self.pra_low)*3600.0
        self.ddec_low = (self.DEC - self.pdec_low)*3600.0
        self.lnL_RA = lnL_RA
        self.lnL_DEC = lnL_DEC
        self.BIC_RA = BICS[0]
        self.BIC_DEC = BICS[1]
        self.BIC_RA_low = BICS[2]
        self.BIC_DEC_low = BICS[3]
        self.b_ra = b_ra[:]
        self.b_dec = b_dec[:]
        self.b_ra_low = b_ra_low[:]
        self.b_dec_low = b_dec_low[:]

        w = np.where(self.goodMatches)
        self.std_ra = np.std(self.dra[w])
        self.std_dec = np.std(self.ddec[w])
        self.std_ra_low = np.std(self.dra_low[w])
        self.std_dec_low = np.std(self.ddec_low[w])

        self._orderToKill()

        self._resid4Panel()

    def _solveMatrix(self):

        w = np.where(self.goodMatches)

        #solve for the solution coefficients
        X = np.copy(self.X[w])
        Y = np.copy(self.Y[w])
        RA = np.copy(self.RA[w])
        DEC = np.copy(self.DEC[w])

        X2 = X*X
        X3 = X2*X
        Y2 = Y*Y
        Y3 = Y2*Y
        XY = X*Y

        #cubed order
        A = np.zeros( (8, len(RA)) ).astype('float64')
        A[0,:] = 1.0
        A[1,:] = X
        A[2,:] = Y
        A[3,:] = X2
        A[4,:] = XY
        A[5,:] = Y2
        A[6,:] = X3
        A[7,:] = Y3
        At = A
        A = At.T

        AtA = np.dot(At,A)
        AtAi = linalg.inv(AtA)
        AtAiAt = np.dot(AtAi,At)
        b_ra = np.dot(AtAiAt,RA)
        b_dec = np.dot(AtAiAt,DEC)


        #squared order
        A = np.zeros( (6, len(RA)) ).astype('float64')
        A[0,:] = 1.0
        A[1,:] = X
        A[2,:] = Y
        A[3,:] = X2
        A[4,:] = XY
        A[5,:] = Y2
        At = A
        A = At.T

        AtA = np.dot(At,A)
        AtAi = linalg.inv(AtA)
        AtAiAt = np.dot(AtAi,At)
        b_ra_low = np.dot(AtAiAt,RA)
        b_dec_low = np.dot(AtAiAt,DEC)



        #now get the ra/dec predictions
        X = np.copy(self.X)
        Y = np.copy(self.Y)
        RA = np.copy(self.RA)
        DEC = np.copy(self.DEC)

        X2 = X*X
        X3 = X2*X
        Y2 = Y*Y
        Y3 = Y2*Y
        XY = X*Y

        #cubed order
        A = np.zeros( (8, len(RA)) ).astype('float64')
        A[0,:] = 1.0
        A[1,:] = X
        A[2,:] = Y
        A[3,:] = X2
        A[4,:] = XY
        A[5,:] = Y2
        A[6,:] = X3
        A[7,:] = Y3
        A = A.T

        predRA = np.dot(A,b_ra)
        predDEC = np.dot(A,b_dec)


        #squared order
        A = np.zeros( (6, len(RA)) ).astype('float64')
        A[0,:] = 1.0
        A[1,:] = X
        A[2,:] = Y
        A[3,:] = X2
        A[4,:] = XY
        A[5,:] = Y2
        A = A.T

        predRA_low = np.dot(A,b_ra_low)
        predDEC_low = np.dot(A,b_dec_low)



        #these seem in error
        lnL_RA = np.sum( -(3600.0*(RA[w]-predRA[w]))**2/(2*self.dX2[w]) )  - np.sum(0.5*np.log(2*np.pi*self.dX2[w]))
        lnL_DEC = np.sum( - (3600.0*(DEC[w] - predDEC[w]))**2/(2*self.dY2[w]))  - np.sum(0.5*np.log(2*np.pi*self.dY2[w]) )

        lnL_RA_low = np.sum( -(3600.0*(RA[w]-predRA_low[w]))**2/(2*self.dX2[w]) ) - np.sum(0.5*np.log(2*np.pi*self.dX2[w]))
        lnL_DEC_low = np.sum( - (3600.0*(DEC[w] - predDEC_low[w]))**2/(2*self.dY2[w]) )  - np.sum(0.5*np.log(2*np.pi*self.dY2[w]))

        BIC_RA = -2*lnL_RA + np.log(len(w[0]))*8
        BIC_RA_low = -2*lnL_RA_low + np.log(len(w[0]))*6
        BIC_DEC = -2*lnL_DEC + np.log(len(w[0]))*8
        BIC_DEC_low = -2*lnL_DEC_low + np.log(len(w[0]))*6
        #print lnL_RA_low,lnL_RA,BIC_RA_low,BIC_RA
        #print lnL_DEC_low,lnL_DEC,BIC_DEC_low,BIC_DEC
        #print lnL_RA,lnL_DEC
        #print lnL_RA_low,lnL_DEC_low

        return (A, b_ra, b_dec, b_ra_low, b_dec_low, predRA, predDEC, predRA_low, predDEC_low, (lnL_RA,lnL_RA_low), (lnL_DEC,lnL_DEC_low), (BIC_RA,BIC_DEC,BIC_RA_low,BIC_DEC_low))


    def xy2sky(self,xy,useLowOrder = False):
        x = xy[:,0]-self._xo
        y = xy[:,1]-self._yo

        x2 = x*x
        x3 = x2*x
        y2 = y*y
        y3 = y2*y
        xy = x*y

        if useLowOrder:
            A = np.ones((6, len(x2))).astype('float64')
            A[1,:] = x
            A[2,:] = y
            A[3,:] = x2
            A[4,:] = xy
            A[5,:] = y2
        else:
            A = np.ones((8, len(x2))).astype('float64')
            A[1,:] = x
            A[2,:] = y
            A[3,:] = x2
            A[4,:] = xy
            A[5,:] = y2
            A[6,:] = x3
            A[7,:] = y3
        A=A.T

        if useLowOrder:
            ra = np.dot(A,self.b_ra_low)
            dec = np.dot(A,self.b_dec_low)
        else:
            ra = np.dot(A,self.b_ra)
            dec = np.dot(A,self.b_dec)
        coords = np.zeros((len(ra),2)).astype('float64')
        coords [:,0] = ra
        coords [:,1] = dec
        return coords




    def updateHeader(self):

        self.header.set('XO',self._xo)
        self.header.set('YO',self._yo)
        for i in range(len(self.goodMatches)):
            self.header.set('XS_{}'.format(i),self.X[i])
            self.header.set('YS_{}'.format(i),self.Y[i])
            self.header.set('dX2S_{}'.format(i),self.dX2[i])
            self.header.set('dY2S_{}'.format(i),self.dY2[i])
            self.header.set('RAS_{}'.format(i),self.RA[i])
            self.header.set('DECS_{}'.format(i),self.DEC[i])
            self.header.set('GS_{}'.format(i),int(self.goodMatches[i]))

        #for i in range(len(self.X)):
        for i in range(len(self.b_ra)):
            self.header.set('B_RA_{}'.format(i),self.b_ra[i])
            self.header.set('B_DEC_{}'.format(i),self.b_dec[i])
        for i in range(len(self.b_ra_low)):
            self.header.set('B_RA_L{}'.format(i),self.b_ra_low[i])
            self.header.set('B_DEC_L{}'.format(i),self.b_dec_low[i])

        self.header.set('STD_RA',self.std_ra)
        self.header.set('STD_DEC',self.std_dec)
        self.header.set('STD_RA_LOW',self.std_ra_low)
        self.header.set('STD_DEC_LOW',self.std_dec_low)
        self.header.set('NMATCH',len(np.where(self.goodMatches==1)[0]))

    def saveFits(self, fn, clobber = True):
        HDU = fits.PrimaryHDU(self.imagedata, self.header)
        List = fits.HDUList([HDU])
        List.writeto(fn, clobber = clobber)






if __name__ == "__main__":

    import pickle
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('--minBA', default = 0.8,
                      type = float, dest = 'minBA', action = 'store',
                      help = 'Minimum B/A sextractor roundness shape parameter to call a star a star. Lower this a small amount if you have trouble finding stars. DEFAULT = %default')
    parser.add_option('--maxMagDiff', default = 0.5,
                      type = float, dest = 'maxMagDiff', action = 'store',
                      help = 'The maximum magnitude difference between MAG_APER and MAG_AUTO for a source to be considered suitable. DEFAULT = %default')
    parser.add_option('--windowSize', default = 13,
                      type = int, dest = 'window', action = 'store',
                      help = 'Window size for plots. DEFAULT = %default')
    parser.add_option('--tsvPath', default = '.',
                      dest = 'tsvPath', type = 'str', action = 'store',
                      help ='Path to the Orcus PS1 tsv file. DEFAULT = %default')
    (opt,args) = parser.parse_args()

    import approx_pos

    if len(args)>0:
        imagefn = args[0]
    else:
        imagefn = 'EFOSC_Image024_0152_corr.fits'

    with fits.open(imagefn) as han:
        header = han[0].header
        imdata = han[0].data
    header.set('RADECSYSa','FK5')

    #scratch crap pixel value fix
    mean = np.median(imdata[::3,::3])
    w = np.where(imdata<0)
    imdata[w] = mean
    HDU = fits.PrimaryHDU(imdata,header)
    List = fits.HDUList([HDU])
    List.writeto('sex.fits',clobber = True)

    (xo,yo) = 512.0,512.0
    for i in range(len(approx_pos.OV_guesses)):
        if imagefn == approx_pos.OV_guesses[i][0]:
            xo = float(int(approx_pos.OV_guesses[i][1]))
            yo = float(int(approx_pos.OV_guesses[i][2]))

    #run sextractor
    overwriteSexFiles = True
    if overwriteSexFiles:
        os.system('rm OV.sex default.conv def.param')
    if not path.isfile('OV.sex') or overwriteSexFiles:
        scamp.makeParFiles.writeSex('OV.sex',
                                    minArea=3,
                                    threshold=3.,
                                    zpt=26.2,
                                    aperture=8.,
                                    min_radius=2.0,
                                    catalogType='FITS_LDAC',
                                    saturate=64000)
    if not path.isfile('default.conv') or overwriteSexFiles:
        scamp.makeParFiles.writeConv()
    if not path.isfile('def.param') or overwriteSexFiles:
        scamp.makeParFiles.writeParam(numAps=1) #numAps is thenumber of apertures that you want to use. Here we use 1

    scamp.runSex('OV.sex', 'sex.fits' ,options={'CATALOG_NAME':imagefn.replace('.fits','.cat')}, verbose=True)
    catalog = trimCatalog(scamp.getCatalog(imagefn.replace('.fits','.cat'),paramFile='def.param'), minBA = opt.minBA, maxMagDiff = opt.maxMagDiff)

    #for i in range(len(catalog['XWIN_IMAGE'])):
    #    print catalog['XWIN_IMAGE'][i],catalog['YWIN_IMAGE'][i]
    #    if abs(catalog['XWIN_IMAGE'][i]-63)<5 and abs(catalog['YWIN_IMAGE'][i] - 934)<5:
    #        for k in catalog.keys():
    #            print k, catalog[k][i]
    #sys.exit()



    dist = ((xo - catalog['XWIN_IMAGE'])**2 + (yo - catalog['YWIN_IMAGE'])**2)**0.5
    args = np.argsort(dist)
    Orcus_x,Orcus_y = catalog['XWIN_IMAGE'][args[0]],catalog['YWIN_IMAGE'][args[0]]
    print '\n\n\n'
    print 'Orcus found at {:.3f} {:.3f} in image {}'.format(Orcus_x,Orcus_y,imagefn)
    print '\n\n\n'

    imSources = []
    for i in range(len(catalog['XWIN_IMAGE'])):
        astromUncert = (catalog['ERRX2WIN_IMAGE'][i]*0.12**2+catalog['ERRY2WIN_IMAGE'][i]*0.12**2)**0.5
        if astromUncert>0.03: continue
        imSources.append([catalog['XWIN_IMAGE'][i],
                          catalog['YWIN_IMAGE'][i],
                          catalog['MAG_APER'][i]+2.5*np.log10(header['EXPTIME']),
                          catalog['FLUX_AUTO'][i],
                          catalog['ERRX2WIN_IMAGE'][i]*0.12**2,
                          catalog['ERRY2WIN_IMAGE'][i]*0.12**2])
    imSources = np.array(imSources)


    #stellar g-r colour range for wcs matching
    #orcus g-r ~0.44
    starColourRange = [-0.2,1.5]


    useOrcusPS = False
    useNewestOV = True
    #load up stellar colours and mjds.
    if useOrcusPS:
        with open('{}/Orcus_PS.tsv'.format(opt.tsvPath)) as han:
            tsv = han.readlines()
    elif useNewestOV:
        with open('{}/OV_PS_catStars_20170823.dat'.format(opt.tsvPath)) as han:
            tsv = han.readlines()
    else: #this one seems best!
        with open('{}/wesBoxSearch4_k.w.smith.tsv'.format(opt.tsvPath)) as han:
            tsv = han.readlines()

    tsvStars = []
    for i in range(1,len(tsv)):
        s = tsv[i].split()
        tsvStars.append([float(s[1]), #ra
                         float(s[2]), #dec
                         float(s[3]), #g
                         float(s[5])]) #r
    tsvStars = np.array(tsvStars)
    w = np.where((tsvStars[:,2]-tsvStars[:,3]>starColourRange[0])&(tsvStars[:,2]-tsvStars[:,3]<starColourRange[1]))
    tsvStars = tsvStars[w]

    ms_wcs = matrixWCSSolver(imdata, header, imSources, tsvStars, windowSize = opt.window, xo=xo, yo=yo)
    ms_wcs.initialMatch()
    #with open('test.pickle','w+') as han:
    #    pickle.dump(ms_wcs.matches,han)

    #with open('test.pickle') as han:
    #    matches = pickle.load(han)
    #    ms_wcs.matches = matches[:]

    ms_wcs.solveMatrix(useLowOrder = True)
    ms_wcs.updateHeader()
    (Orcus_ra,Orcus_dec) = ms_wcs.xy2sky(np.array([[Orcus_x,Orcus_y]]))[0]
    ms_wcs.header.set('Orc_RA',Orcus_ra)
    ms_wcs.header.set('Orc_DEC',Orcus_dec)
    ms_wcs.saveFits('{}_wcs.fits'.format(imagefn.replace('.fits','')))
