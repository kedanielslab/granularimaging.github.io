"""
Excerpted by Karen Daniels from:
https://github.com/Jfeatherstone/pepe
17 November 2023
"""

"""
Generate a synthetic photoelastic response.
"""
import numpy as np

import numba

def circularMask(size, center, radius, channels=3):
    """
    Create a mask in the shape of a circle, in which the inside of the circle is
    the desired region.

    Parameters
    ----------

    size : [int, int] or [int, int, int]
        The size of the mask to be created (height, width[, channels]). Can include number of channels.
        If not included, default is 3; see `channels`.

    center : [int, int]
        The [y, x] coordinates of the center of the desired region. 

    radius : int
        The radius of the desired region.

    channels : int
        The number of channels to create for the mask, if not included in `size` parameter.

    Returns
    -------

    np.uint8[3] : Mask array (height, width, channels)
    """

    # If channels are included in the size, use that
    if len(size) == 3:
        channels = size[2]

    # numba doesn't support ogrid, so we just do it manually
    #Y, X = np.ogrid[:size[0], :size[1]]
    Y = np.arange(size[0]).reshape((size[0], 1)) # Column vector
    X = np.arange(size[1]).reshape((1, size[1])) # Row vector

    dist_from_center = np.sqrt((X - center[1])**2 + (Y-center[0])**2)

    maskArr = np.zeros((size[0], size[1], channels), np.uint8)
    for i in range(channels):
        maskArr[:,:,i] = dist_from_center <= radius

    return maskArr
    

def genSyntheticResponse(forceArr, alphaArr, betaArr, fSigma, radius, pxPerMeter=1, brightfield=True, imageSize=None, center=None, mask=None):
    """
    Generate the theoretical photoelastic response given the material
    properties and a set of forces.

    Based on Jonathan Kollmer's PeGS (matlab):
    https://github.com/jekollmer/PEGS

    and Olivier Lantsoght's PeGS_Py:
    https://git.immc.ucl.ac.be/olantsoght/pegs_py

    Parameters
    ----------

    forceArr : np.ndarray[Z]
        Array of force magnitudes acting on the particle (Z is number of contacts
        aka coordination number)

    alphaArr : np.ndarray[Z]
        Array of angles representing force contact angles.

    betaArr : np.ndarray[Z]
        Array of angles representing force contact positions.

    fSigma : float
        Stress optic coefficient, relating to material thickness, wavelength of light
        and other material property (C).

    radius : float
        Radius of the particle that is being simulated in pixels. If pxPerMeter is
        set to None, this value will be assumed to already have been converted to meters.

    pxPerMeter : float
        The number of pixels per meter for the simulated image. If not provided (or set to 1), the radius
        value will be assumed to already have been converted to meters.

    brightfield : bool
        Whether the intensity should be simulated as seen through a brightfield (True)
        polariscope or darkfield (False) polariscope.

    imageSize : tuple(np.int64[2]) or None
        The size of the canvas the stress pattern will be drawn on. Set to None to automatically
        determine this based on the radius.

    center : np.float64[2] or None
        Where the center of the particle should be position in on the image canvas. Useful for
        creating a composite image of many particles, as the final image can be made just by
        adding each individual matrix together. Set to None to center the particle automatically.

    mask : np.uint8[H,W]
        Array of values representing which points, within the circle, to calculate the intensity
        for. Points with non-zero value represented desired points, and locations with value of
        0 will not be calculated.

        Points with value of 1 outside of the circular particle will be ignored.

    """

    # Deal with parameters about the image
    # Note that it is very helpful to have an odd size, such that there is
    # a central pixel
    if imageSize is None:
        # 11 is arbitrary, just a small, odd number
        imageSize = (np.int64(radius*2)+11, np.int64(radius*2)+11)

    if center is None:
        center = np.array([imageSize[0]/2, imageSize[1]/2], dtype=np.float64)

    if mask is None:
        mask = circularMask(imageSize, center, radius)[:,:,0]

    # Create a mask representing the particle, to find the points we need
    # to simulate
    particleMask = circularMask(imageSize, center, radius)[:,:,0]
    # Grab every point inside the circle

    # Normally we could just do this:
    #points = np.transpose(np.where(cMask > 0))
    # but numba doesn't quite like this way, so we have to be 
    # a little more creative
    fullMask = particleMask + mask
    whereIndices = np.where(fullMask > 1)
    points = np.zeros((len(whereIndices[0]), 2), dtype=np.int64)
    # There is a chance that these indices are backwards, but
    # because we have rotational symmetry, it doesn't really matter...
    # BUT if there is ever some weird anisotropy bug or something,
    # try switching these indices
    points[:,0] = whereIndices[0]
    points[:,1] = whereIndices[1]

    intensityArr = np.zeros((imageSize[0], imageSize[1]))

    # As per conventions through the rest of the library, order of points is y,x
    for i in numba.prange(points.shape[0]):
        # While we index for the points on the entire grid,
        # we have to pass the stress evaluation method the position relative
        # to the center of the partice
        intensityArr[points[i,0],points[i,1]] = evaluateStress(points[i,0]-center[0], points[i,1]-center[1], forceArr, alphaArr, betaArr, fSigma, radius, pxPerMeter, brightfield)

    return intensityArr
    

# See genSyntheticResponse note about fastmath
@numba.njit(fastmath=True)
def evaluateStress(yInd, xInd, forceArr, alphaArr, betaArr, fSigma, radius, pxPerMeter, brightfield=True):
    """
    Evaluate the stress (and resulting photoelastic intensity) at a particular point within
    a particle subject to a set of forces. 

    No checks are done to insure that the point provided is within the particle itself -- this
    should be done externally.

    Parameters
    ----------

    yInd : int
        The indexed y of the point we are computing the stress for, relative
        to the center of the particle.

    xInd : int
        The indexed x of the point we are computing the stress for, relative
        to the center of the particle.

    forceArr : np.ndarray[Z]
        Array of force magnitudes acting on the particle (Z is number of contacts,
        aka coordination number).

    alphaArr : np.ndarray[Z]
        Array of angles representing force contact angles.

    betaArr : np.ndarray[Z]
        Array of angles representing force contact positions.

    fSigma : float
        Stress optic coefficient, relating to material thickness, wavelength of light
        and other material property (C).

    radius : float
        Radius of the particle that is being simulated in pixels. If pxPerMeter is
        set to None, this value will be assumed to already have been converted to meters.

    pxPerMeter : float
        The number of pixels per meter for the simulated image. While not recommended,
        set value to 1 if the positions and radius have already been converted to meters.

    brightfield : bool
        Whether the intensity should be simulated as seen through a brightfield (True)
        polariscope or darkfield (False) polariscope.
        
    """
    # We expect that distance/position values are NOT in physical units yet
    # so we have to divide by pxPerMeter to get real values
    xM = xInd/pxPerMeter
    yM = yInd/pxPerMeter
    radiusM = radius/pxPerMeter

    # Coordination number
    z = len(forceArr)

    # Iterate over each force, and calculate the total stress
    # attributed to that force (at the given point)
    sigmaXX, sigmaXY, sigmaYY = 0,0,0
    for i in range(z):
        # Adjust beta for rotation to match the real images we are working with
        b1 = -betaArr[i] + np.pi
        # The middle expression is really just the sign function, but we
        # need sign(0)=1 (sign(0)=0 by default) so we do a little
        # boolean magic
        b2 = b1 - (-1 + 2*int(np.sign(alphaArr[i]) > -1)) * np.pi + 2*alphaArr[i]

        # Calculate the length of the chord
        chordX = radiusM * (np.sin(b2) - np.sin(b1))
        chordY = radiusM * (np.cos(b2) - np.cos(b1))
        chordLength = np.sqrt(chordX**2 + chordY**2)

        # Calculate the vector for the given position to the chord
        vecX = xM - radiusM*np.sin(b1)
        vecY = -yM - radiusM*np.cos(b1) # Not sure why there is negative here
        rVec = np.sqrt(vecX**2 + vecY**2)

        # Error check
        # See if either the vector or the chord length is zero
        if rVec*chordLength == 0.:
            #print("Bad length")
            return 0.

        # Normalize the components of the chord
        chordX /= chordLength
        chordY /= chordLength

        arccosArgument = (vecX*chordX + vecY*chordY) / rVec

        # At the very center, this argument will be almost exactly 1,
        # but we'll get a nan if it is exactly 1, so we need to subtract a little
        # bit slightly above the order of machine error
        # This is most likely the issue that Jonathan commented about in his code
        #arccosArgument -= np.float64(xInd+yInd + xInd*yInd == 0)*1e-10
        arccosArgument -= 1e-10

        th = np.sign(vecY*chordX - vecX*chordY) * np.arccos(arccosArgument)

        s1 = -2/np.pi * forceArr[i]*arccosArgument / rVec
        s2 = -1/(np.pi*radiusM) * forceArr[i] * (-np.sin(alphaArr[i]))
        sr = s1 #- s2 testing bug fix from Nov 2023 Alexandria session

        th += betaArr[i] - np.pi/2 - alphaArr[i]

        sigmaXX += sr*np.sin(th)**2
        sigmaYY += sr*np.cos(th)**2
        sigmaXY += 0.5*s1*np.sin(2*th)

    pressureDiff = sigmaXX - sigmaYY
    principleStressDiff = np.sqrt(pressureDiff**2 + 4*sigmaXY**2)

    # Brightfield vs darkfield we use cos vs sin
    if brightfield:
        return np.cos(np.pi/fSigma * principleStressDiff)**2
    else:
        return np.sin(np.pi/fSigma * principleStressDiff)**2
