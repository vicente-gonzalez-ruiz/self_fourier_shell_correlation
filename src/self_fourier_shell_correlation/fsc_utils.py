"""
Author: Eric Verbeke
"""

import time
import numpy as np
import scipy.ndimage as ndi
from scipy.special import jv

def log_abs(array):
    return np.log(1 + np.abs(array))

def ft2(array):
    return np.fft.fftshift(np.fft.fft2(array))

def ift2(array):
    return np.fft.ifft2(np.fft.ifftshift(array)).real

def ftn(array):
    return np.fft.fftshift(np.fft.fftn(array))

def iftn(array):
    return np.fft.ifftn(np.fft.ifftshift(array)).real

def open_mrc(mrc_file, return_voxel=False):
    with mrcfile.open(mrc_file) as mrc:
        v = mrc.data
        voxel = mrc.voxel_size.x
        mrc.close()
        if return_voxel:
            v = [v, voxel]
    return x

def radial_distance_grid(shape):
    """Compute grid of radial distances"""
    
    center = [n//2 for n in shape]
    idx = [slice(-center[i], l-center[i]) for i, l in enumerate(shape)] 
    coords = np.ogrid[idx] # zero-centered grid index
    square_coords = [c**2 for c in coords] # square grid for distance (x^2 + y^2 + z^2 = r^2)
    
    radial_dists = square_coords[0] # initialize to broadcast distance grid by dimension
    for dimension in range(1, len(shape)):
        radial_dists = radial_dists + square_coords[dimension]
        
    return np.round(np.sqrt(radial_dists))

def shell_mask(r_dists, r_o, dr=1):
    """Returns shell mask as boolean"""
    
    outer = r_dists <= r_o
    inner = r_dists <= (r_o - dr)
    
    mask = np.logical_xor(outer, inner)
    
    return mask

def sphere_mask(r_dists, radius=False):
    """Returns sphere mask as boolean"""
    
    if not radius:
        center = [n//2 for n in r_dists.shape]
        radius = np.amin(center)
        
    mask = r_dists <= radius
    
    return mask

def product(*args):
    """Cartesian product from python 3 itertools"""
    
    pools = [tuple(pool) for pool in args]
    result = [[]]
    for pool in pools:
        result = [x+[y] for x in result for y in pool]
    for prod in result:
        yield tuple(prod)
    
def split_array(array):
    """
    Downsample an even square array into combinations of even/odd indicies
    Example of 2D array split, grouped by number
     ___ ___ ___ ___
    |_0_|_1_|_0_|_1_|
    |_2_|_3_|_2_|_3_| 
    |_0_|_1_|_0_|_1_|
    |_2_|_3_|_2_|_3_|
  
    """

    shape = array.shape
    
    even = slice(None, None, 2)
    odd = slice(1, None, 2)
    
    pairs = [[even, odd] for dimension in range(len(shape))]
    
    split_idx = list(product(*pairs))
    
    split = np.array([array[idx] for idx in split_idx])
    
    return split

def trim_edges(array):
    """Trim length of each dimension by 1"""
    
    shape = array.shape
    trim_idx = tuple([slice(0, l-1) for l in shape])
    trim_array = array[trim_idx]
    
    return trim_array

def get_split_array(array):
    """Split array and make even dimensions by truncating if necessary"""
    
    shape = array.shape

    assert len(np.unique(shape)) == 1, "input must have equal size dimensions"

    if shape[0] % 2 != 0:
        array = trim_edges(array)

    split = split_array(array)

    split_shape = split[0].shape

    if split_shape[0] % 2 != 0:
        split = np.array([trim_edges(s) for s in split])
            
    return split

def phase_shift_2d(F, sx, sy):
    """Phase shift 2-D array, requires even shape"""
    
    Ny, Nx = F.shape
    
    for N in [Ny, Nx]:
        assert N % 2 == 0, "array needs even dimensions"

    ky = np.arange(-Ny//2, Ny//2).reshape(Ny,1)
    kx = np.arange(-Nx//2, Nx//2).reshape(1,Nx)

    wy = np.exp(-2*np.pi*1j*sy*ky/Ny)
    wx = np.exp(-2*np.pi*1j*sx*kx/Nx)

    F_shift = wy * wx * F
    
    return F_shift

def phase_shift_3d(F, sx, sy, sz):
    """Phase shift 3-D array, requires even shape"""

    Nz, Ny, Nx = F.shape
    
    for N in [Nz, Ny, Nx]:
        assert N % 2 == 0, "array needs even dimensions"
    
    kz = np.arange(-Nz//2, Nz//2).reshape(Nz,1,1)
    ky = np.arange(-Ny//2, Ny//2).reshape(1,Ny,1)
    kx = np.arange(-Nx//2, Nx//2).reshape(1,1,Nx)

    wz = np.exp(-2*np.pi*1j*sz*kz/Nz)
    wy = np.exp(-2*np.pi*1j*sy*ky/Ny)
    wx = np.exp(-2*np.pi*1j*sx*kx/Nx)

    F_shift = wz * wy * wx * F
    
    return F_shift


def compute_fourier_shell_correlation(Y1, Y2, rmax, gamma=1/4, whiten_upsample=False):
    """
    Compute the normalized correlation from FT of array
    inputs  : Y1, Y2, ring/shell thickness
    returns : 1D array of correlation values
    """
    
    assert Y1.shape == Y2.shape, "arrays must be same shape"
    
    shape = Y1.shape
    print(f"compute_fourier_shell_correlation.shape={shape}")
    
    rdists = radial_distance_grid(shape) 
    
    index = np.unique(rdists)[:rmax]

    top = np.conj(Y1) * Y2
    bot1 = np.abs(Y1)**2
    bot2 = np.abs(Y2)**2
    
    t = ndi.mean(top.real, rdists, index)
    b1 = ndi.mean(bot1.real, rdists, index) 
    b2 = ndi.mean(bot2.real, rdists, index)
    
    if whiten_upsample:
        t = t - gamma
    
    corr = t / np.sqrt(b1 * b2)

    return corr


def single_image_frc(image, rmax, n_splits=1, whiten_upsample=False):
    """
    Computes the SFSC for a 2D array, specify it the array is whitened and upsampled.
    n_splits is number of dimensions to split into even and odd terms (only supports 1 and 2).
    Returns array of correlations.
    """
    
    corrs = []
    
    if n_splits == 1:

        slices = get_slices(d=2)
        shifts = [[0.5, 0], 
                  [0, 0.5]]
        
        for i, s in enumerate(slices):
            y1 = image[s[0][0], s[0][1]]
            y2 = image[s[1][0], s[1][1]]
            
            Y1 = ft2(y1)
            Y2 = phase_shift_2d(ft2(y2), shifts[i][0], shifts[i][1])
            
            
            if whiten_upsample:
                corr = compute_fourier_shell_correlation(Y1, Y2, rmax, whiten_upsample=True)
            else:
                corr = compute_fourier_shell_correlation(Y1, Y2, rmax)
            
            corrs.append(corr)
        
        corrs = np.array(corrs)
        
    elif n_splits == 2:
        
        rmax = rmax // 2
        a = get_shifts(d=2)
        
        y = get_split_array(image)
        Y = np.fft.fftshift(np.fft.fft2(y), axes=(1,2))
        
        c = 0 # index counter for shifts
        
        for i in range(4):
            Y1 = Y[i]
            for j in range(i+1, 4):
                Y2 = phase_shift_2d(Y[j], a[c][0], a[c][1])
                if whiten_upsample:
                    corr = compute_fourier_shell_correlation(Y1, Y2, rmax, whiten_upsample=True)
                else:
                    corr = compute_fourier_shell_correlation(Y1, Y2, rmax)
                corrs.append(corr)
                c += 1
                
    corrs = np.array(corrs)
                
    return corrs


def single_volume_fsc(volume, rmax, n_splits=1, whiten_upsample=False):
    """
    Computes the SFSC for a 3D array, specify it the array is whitened and upsampled.
    n_splits is number of dimensions to split into even and odd terms (only supports 1 and 3).
    Returns array of correlations.
    """
    corrs = []
    
    shape = volume.shape
    center = shape[0] // 2
    
    lb = center - rmax
    ub = center + rmax
    
    if n_splits == 1:
        
        slices = get_slices(d=3)   
        shifts = [[0.5, 0, 0],
                  [0, 0.5, 0],
                  [0, 0, 0.5]]
        
        for i, s in enumerate(slices):
            y1 = volume[s[0][0], s[0][1], s[0][2]]
            y2 = volume[s[1][0], s[1][1], s[1][2]]
            
            Y1 = ftn(y1)
            Y2 = phase_shift_3d(ftn(y2), shifts[i][0], shifts[i][1], shifts[i][2])
            
            # crop to rmax to speed up FSC, fix this style later, add this to 2D as well
            if i == 0:
                Y1 = Y1[lb:ub, lb:ub, :]
                Y2 = Y2[lb:ub, lb:ub, :]
            elif i == 1:
                Y1 = Y1[lb:ub, :, lb:ub]
                Y2 = Y2[lb:ub, :, lb:ub]
            elif i == 2:
                Y1 = Y1[:, lb:ub, lb:ub]
                Y2 = Y2[:, lb:ub, lb:ub]
                
            if whiten_upsample:
                corr = compute_fourier_shell_correlation(Y1, Y2, rmax, whiten_upsample=True)
            else:
                corr = compute_fourier_shell_correlation(Y1, Y2, rmax)

            corrs.append(corr)
        
    elif n_splits == 3:
        
        rmax = rmax // 2    
        a = get_shifts(d=3)

        y = get_split_array(volume)        
        Y = np.fft.fftshift(np.fft.fftn(y, axes=(1,2,3)), axes=(1,2,3))
        
        c = 0 # index counter for shifts
        
        for i in range(8):
            Y1 = Y[i]
            for j in range(i+1, 8):
                Y2 = phase_shift_3d(Y[j], a[c][0], a[c][1], a[c][2])
                if whiten_upsample:
                    corr = compute_fourier_shell_correlation(Y1, Y2, rmax, whiten_upsample=True)
                else:
                    corr = compute_fourier_shell_correlation(Y1, Y2, rmax)
                corrs.append(corr)
                c += 1
                
    corrs = np.array(corrs)
    
    return corrs


def two_image_frc(image_1, image_2, rmax):
    """Computes the two-imag FRC, nput is a pair of real space volumes"""
    
    assert image_1.shape == image_2.shape, "input shape mismatch"
    
    image_1_ft = ft2(image_1)
    image_2_ft = ft2(image_2)
    
    two_image_frc = compute_fourier_shell_correlation(image_1_ft, image_2_ft, rmax)
    
    return two_image_frc   


def two_volume_fsc(volume_1, volume_2, rmax):
    """Computes the two-volume FSC, nput is a pair of real space volumes"""
    
    assert volume_1.shape == volume_2.shape, "input shape mismatch"
    
    volume_1_ft = ftn(volume_1)
    volume_2_ft = ftn(volume_2)
    
    two_volume_fsc = compute_fourier_shell_correlation(volume_1_ft, volume_2_ft, rmax)
    
    return two_volume_fsc


def get_radial_spatial_frequencies(array, voxel_size, mode='full'):

    if mode == 'split':
        split = get_split_array(array)
        array = split[0] 
        voxel_size = 2*voxel_size
        
    r = np.amax(array.shape)  
    r_freq = np.fft.fftfreq(r, voxel_size)[:r//2]
    
    return r_freq


def compute_spherically_averaged_power_spectrum(array, rmax):
    
    shape = array.shape

    F = ftn(array)

    rdists = radial_distance_grid(shape)
    index = np.unique(rdists)[:rmax]
    spherically_averaged_power_spectrum = ndi.mean(abs(F)**2, rdists, index)
    
    return spherically_averaged_power_spectrum


def low_pass_filter(array, voxel_size, resolution):
    """Low pass filter array to specified resolution"""

    n = array.shape[0]

    assert resolution >= ((n - 2) / (2*n*voxel_size))**-1, "specified resolution greater than Nyquist"
    
    freq = get_radial_spatial_frequencies(array, voxel_size)  
    res = np.array([1/f if f > 0 else 0 for f in freq])
    radius = np.where(res <= resolution)[0][1]

    r_dists = radial_distance_grid(array.shape)
    lpf_mask = sphere_mask(r_dists, radius)
    
    F = ftn(array)
    F_lpf = F * lpf_mask
    f_lpf = iftn(F_lpf)
    
    return f_lpf


def b_factor_function(shape, voxel_size, B):
    """B factor equation as function of spatial frequency"""
    
    N = shape[0]
    
    spatial_frequency = np.fft.fftshift(np.fft.fftfreq(N, voxel_size))

    sf_grid = np.meshgrid(*[spatial_frequency**2 for dimension in range(len(shape))])

    square_sf_grid = sf_grid[0] # initialize to broadcast by dimension
    for dimension in range(1, len(shape)):
        square_sf_grid = square_sf_grid + sf_grid[dimension]
    
    G = np.exp(- square_sf_grid * (B/4))
    
    return G


def zero_order_bessel(frequency, shift, pixel_size, mode='full'):
    """scale zero order Bessel function of the first kind to match FRC, shift is 2D vector"""
    
    if mode == 'split':
        scale = 2*pixel_size*2*np.pi*np.linalg.norm(shift) 
    else:
        scale = pixel_size*2*np.pi*np.linalg.norm(shift)
    
    B = jv(0, scale*frequency) # J0(pixel_size*2pi*||a||*xi)
    
    return B


def get_sigma_for_snr(x, snr):
    """return standard deviation of WGN for desired snr given real array x"""
    
    N = x.size
    signal = np.sum(x**2)
    noise = np.sqrt(signal / (snr * N))
    
    return noise


def apply_b_factor(v, voxel, B_signal):
    """return array after applying B-factor decay, input is real array"""
    
    G = b_factor_function(v.shape, voxel, B_signal)
    V = ftn(v)
    Vb = G * V
    vb = iftn(Vb)
    
    return vb


def generate_noise(noise_std, shape, voxel, B_noise=False):
    """Generate white or color Gaussian noise with B-factor decay"""
    
    eps = np.random.normal(0, noise_std, shape)
    
    if B_noise:
        G = b_factor_function(shape, voxel, B_noise)
        eta = ftn(eps) * G
        eps = iftn(eta)
        
    return eps


def generate_noisy_data(v, voxel, snr, B_signal=False, B_noise=False, return_noise=False):
    """Function to generate noisy data with B-factor decay and color Gaussian noise"""
    
    noise_std = get_sigma_for_snr(v, snr) # sigma is computed for array prior to adding B-factor
    
    eps = generate_noise(noise_std, v.shape, voxel, B_noise)
    
    if B_signal:
        v = apply_b_factor(v, voxel, B_signal)
    
    y = v + eps
    
    if return_noise:
        return y, eps
    else:
        return y
    
    
def whitening_transform(y, noise, rmax, ratio=1):
    """
    Whiten transform array (y) with known noise variance (noise).
    Ratio is a scaling parameter if the noise variance is estimated from a different size array.
    """
    
    rdists = radial_distance_grid(y.shape)
    
    noise_raps = compute_spherically_averaged_power_spectrum(noise, rmax) / ratio
    
    Y = ftn(y)
    
    for ri in range(rmax):  # can add option to skip first n low freq shells
        mask = shell_mask(rdists, ri)
        Y[mask] = (1 / np.sqrt(noise_raps[ri])) * Y[mask]
        
    y_whitened = iftn(Y)
    
    return y_whitened


def fourier_upsample(array, factor=1, rescale=False):
    """Upsample array by zero-padding its Fourier transform (factor 2 would give 100pix -> 200pix)"""
    
    assert factor >= 1, "scale factor must be greater than 1"
    
    shape = array.shape
    
    F = ftn(array)
    p = int((shape[0] * (factor-1)) / 2)
    F_upsample = np.pad(F, p)
    
    if rescale:
        F_upsample = F_upsample * (np.product(F_upsample.shape) / np.product(F.shape))
    
    f_upsample = iftn(F_upsample)
    
    return f_upsample


def fourier_downsample(array, factor=1, rescale=False):
    """Downsample array by cropping its Fourier transform (factor 2 would give 100pix -> 50pix)"""
    
    assert factor >= 1, "scale factor must be greater than 1"
    
    shape = array.shape
    center = [d//2 for d in shape]
    new_shape = [int(d / factor) for d in shape]
    
    F = ftn(array)
    idx = tuple([slice(center[i] - new_shape[i]//2, center[i] + new_shape[i]//2) for i in range(len(shape))])
    F = F[idx] 
    
    if rescale:
        F = F * (np.product(new_shape) / np.product(shape))
    
    f_downsample = iftn(F)
    
    return f_downsample


def linear_interp_resolution(fsc, frequencies, v=1/7):
    """Estimate FSC at first crossing of value (v) by linear interpolation"""
   
    w = np.where(fsc <= v)[0]
    
    if w.size > 0:
        x1, x2 = frequencies[w[0]], frequencies[w[0]-1]
        y1, y2 = fsc[w[0]], fsc[w[0]-1]

        m = (y2 - y1) / (x2 - x1)
        b = y1 - m*x1

        resolution = np.round(1 / ((v - b) / m), 2)
        
    else:
        resolution = 'None'
    
    return resolution


def get_slices(d):
    """returns slice index for splitting 2-D or 3-D array into even and odd terms along each dimension"""
    
    if d == 2:
        slices = [
            [[slice(None), slice(None, None, 2)], [slice(None), slice(1, None, 2)]], # split by column
            [[slice(None, None, 2), slice(None)], [slice(1, None, 2), slice(None)]]  # split by row
        ]       
        
    elif d == 3:
        slices = [
            [[slice(None), slice(None), slice(None, None, 2)], [slice(None), slice(None), slice(1, None, 2)]], # split column
            [[slice(None), slice(None, None, 2), slice(None)], [slice(None), slice(1, None, 2), slice(None)]], # split row
            [[slice(None, None, 2), slice(None), slice(None)], [slice(1, None, 2), slice(None), slice(None)]]  # split layer
        ]  
    
    return slices


def get_shifts(d):
    """
    returns shift value for decimated array split over d-dimensions
    e.g. for a 4x4 array
     ___ ___ ___ ___
    |_0_|_1_|_0_|_1_|
    |_2_|_3_|_2_|_3_| 
    |_0_|_1_|_0_|_1_|
    |_2_|_3_|_2_|_3_|
  
    """
    
    if d == 2:
        a = [( 0.5, 0.0),   # (0, 1) 0
             ( 0.0, 0.5),   # (0, 2) 1
             ( 0.5, 0.5),   # (0, 3) 2
             (-0.5, 0.5),   # (1, 2) 3
             ( 0.0, 0.5),   # (1, 3) 4
             ( 0.5, 0.0)]   # (2, 3) 5

    elif d == 3:
        a = [( 0.5,  0.0, 0.0),   # (0, 1) 0
             ( 0.0,  0.5, 0.0),   # (0, 2) 1
             ( 0.5,  0.5, 0.0),   # (0, 3) 2
             ( 0.0,  0.0, 0.5),   # (0, 4) 3
             ( 0.5,  0.0, 0.5),   # (0, 5) 4
             ( 0.0,  0.5, 0.5),   # (0, 6) 5
             ( 0.5,  0.5, 0.5),   # (0, 7) 6
             (-0.5,  0.5, 0.0),   # (1, 2) 7
             ( 0.0,  0.5, 0.0),   # (1, 3) 8
             (-0.5,  0.0, 0.5),   # (1, 4) 9
             ( 0.0,  0.0, 0.5),   # (1, 5) 10
             (-0.5,  0.5, 0.5),   # (1, 6) 11
             ( 0.0,  0.5, 0.5),   # (1, 7) 12
             ( 0.5,  0.0, 0.0),   # (2, 3) 13
             ( 0.0, -0.5, 0.5),   # (2, 4) 14
             ( 0.5, -0.5, 0.5),   # (2, 5) 15
             ( 0.0,  0.0, 0.5),   # (2, 6) 16
             ( 0.5,  0.0, 0.5),   # (2, 7) 17
             (-0.5, -0.5, 0.5),   # (3, 4) 18
             ( 0.0, -0.5, 0.5),   # (3, 5) 19
             (-0.5,  0.0, 0.5),   # (3, 6) 20
             ( 0.0,  0.0, 0.5),   # (3, 7) 21
             ( 0.5,  0.0, 0.0),   # (4, 5) 22
             ( 0.0,  0.5, 0.0),   # (4, 6) 23
             ( 0.5,  0.5, 0.0),   # (4, 7) 24
             (-0.5,  0.5, 0.0),   # (5, 6) 25
             ( 0.0,  0.5, 0.0),   # (5, 7) 26
             ( 0.5,  0.0, 0.0)]   # (6, 7) 27
        
    return a

def get_SFSC_curve(volume):
    y1 = volume
    s1 = y1[:, :, ::2]
    s2 = y1[:, :, 1::2]
    S2 = phase_shift_3d(np.fft.fftshift(np.fft.fftn(s2)), 0.5, 0, 0)
    s2_shift = np.fft.ifftn(np.fft.ifftshift(S2)).real

    s3 = y1[:, ::2, :]
    s4 = y1[:, 1::2, :]
    S4 = phase_shift_3d(np.fft.fftshift(np.fft.fftn(s4)), 0, 0.5, 0)
    s4_shift = np.fft.ifftn(np.fft.ifftshift(S4)).real

    s5 = y1[::2, :, :]
    s6 = y1[1::2, :, :]
    S6 = phase_shift_3d(np.fft.fftshift(np.fft.fftn(s6)), 0, 0, 0.5)
    s6_shift = np.fft.ifftn(np.fft.ifftshift(S6)).real

    r = volume.shape[0]//2

    c1 = two_volume_fsc(s1, s2_shift, r)
    c2 = two_volume_fsc(s3, s4_shift, r)
    c3 = two_volume_fsc(s5, s6_shift, r)

    c_avg = np.mean([c1, c2, c3], axis=0)

    freq = get_radial_spatial_frequencies(s1, 1)

    return freq, c_avg

def random_split(signal):
    """
    Split the signal into two independent half-signals by dividing the data randomly.
    """
    mask = np.random.randint(0, 2, signal.shape, dtype=bool)
    s1 = np.where(mask, signal, 0)
    s2 = np.where(~mask, signal, 0)
    return s1, s2

def odd_even_split(image):
    s1 = image[:, ::2]
    s2 = image[:, 1::2]
    return s1, s2

def get_SFRC_curve__even_odd(image):
    '''even/odd downsampling'''
    s1 = image[:, ::2]
    s2 = image[:, 1::2]
    #s1, s2 = random_split(image)
    S2 = phase_shift_2d(np.fft.fftshift(np.fft.fftn(s2)), 0.5, 0)
    s2_shift = np.fft.ifftn(np.fft.ifftshift(S2)).real

    s3 = image[::2, :]
    s4 = image[1::2, :]
    #s3, s4 = random_split(image)
    S4 = phase_shift_2d(np.fft.fftshift(np.fft.fftn(s4)), 0, 0.5)
    s4_shift = np.fft.ifftn(np.fft.ifftshift(S4)).real

    r = image.shape[0]//2

    c1 = two_image_frc(s1, s2_shift, r)
    c2 = two_image_frc(s3, s4_shift, r)

    c_avg = np.mean([c1, c2], axis=0)

    c_avg = 2*c_avg / (1 + c_avg)

    freq = get_radial_spatial_frequencies(s1, 1)

    return freq, c_avg

from shuffling import image as image_shuffling

def __get_SFRC_curve__chessboard(image):
    '''even/odd downsampling'''
    blacks = image_shuffling.chessboard_interpolate_blacks(image)
    whites = image_shuffling.chessboard_interpolate_whites(image)

    r = image.shape[0]//2

    c1 = two_image_frc(image, blacks, r)
    c2 = two_image_frc(image, whites, r)

    c_avg = np.mean([c1, c2], axis=0)

    #c_avg = 2*c_avg / (1 + c_avg)

    freq = get_radial_spatial_frequencies(image, 1)

    return freq, c_avg

def get_SFRC_curve__chessboard(image):
    '''even/odd downsampling'''
    blacks = image_shuffling.chessboard_blacks(image)
    whites = image_shuffling.chessboard_whites(image)

    r = image.shape[0]//2

    c_avg = two_image_frc(whites, blacks, r)

    #c_avg = 2*c_avg / (1 + c_avg)

    freq = get_radial_spatial_frequencies(image, 1)

    return freq, c_avg

def get_SFRC_curve__interpolated_chessboard(image):
    '''even/odd downsampling'''
    blacks = image_shuffling.chessboard_interpolate_blacks(image)
    whites = image_shuffling.chessboard_interpolate_whites(image)

    r = image.shape[0]//2

    c_avg = two_image_frc(whites, blacks, r)

    #c_avg = 2*c_avg / (1 + c_avg)

    freq = get_radial_spatial_frequencies(image, 1)

    return freq, c_avg

def get_SFRC_curve__subsampled_chessboard(image):
    # https://www.nature.com/articles/s41467-019-11024-z
    # https://github.com/sakoho81/miplib/blob/public/miplib/processing/image.py#L133

    A, B, C, D = image_shuffling.subsampled_chessboard(image)

    r = image.shape[0]//4

    c1 = two_image_frc(A, B, r)
    c2 = two_image_frc(C, D, r)
    c_avg = np.mean([c1, c2], axis=0)

    #freq = get_radial_spatial_frequencies(image, 1)
    freq = np.arange(0, len(c_avg))/(len(c_avg)*2)

    return freq, c_avg

def get_SFRC_curve__SPRS1(image, N = 10, std_dev=2.0, sigma_poly=1.2, window_side=5):
    '''Structure-Preserving Random shuffling'''
    r = image.shape[0]//2

    acc = np.zeros(r)
    for i in range(N):
        c1 = image_shuffling.randomize_and_project(image, std_dev, window_side, sigma_poly)
        c2 = image_shuffling.randomize_and_project(image, std_dev, window_side, sigma_poly)
        curve = two_image_frc(c1, c2, r)
        acc += curve

    c_avg = acc/(i+1)
    #c_avg = 2*c_avg / (1 + c_avg)
    freq = get_radial_spatial_frequencies(image, 1)

    return freq, c_avg

def get_SFRC_curve__SPRS2(image, N = 10, std_dev=2.5, sigma_poly=1.2, window_side=5):
    '''Structure-Preserving Random shuffling'''
    r = image.shape[0]//2

    acc = np.zeros(r)
    for i in range(N):
        #c1 = image_shuffling.randomize_and_project(image, std_dev, window_side, sigma_poly)
        c2 = image_shuffling.randomize_and_project(image, std_dev, window_side, sigma_poly)
        curve = two_image_frc(image, c2, r)
        acc += curve

    c_avg = acc/(i+1)
    #c_avg = 2*c_avg / (1 + c_avg)
    freq = get_radial_spatial_frequencies(image, 1)

    return freq, c_avg

def __get_SFRC_curve(image):
    '''random downsampling'''
    s1, s2 = random_split(image)
    s3, s4 = random_split(image)
    s5, s6 = random_split(image)

    r = image.shape[0]//2

    c1 = two_image_frc(s1, s2, r)
    c2 = two_image_frc(s3, s4, r)
    c3 = two_image_frc(s5, s6, r)

    c_avg = np.mean([c1, c2, c3], axis=0)

    #c_avg = 2*c_avg / (1 + c_avg)

    freq = get_radial_spatial_frequencies(s1, 1)

    return freq, c_avg

def __get_SFRC_curve(image):
    '''checkboard downsampling'''
    s1 = image[::2, ::2]
    s2 = image[1::2, ::2]
    s3 = image[::2, 1::2]
    s4 = image[1::2, 1::2]

    S2 = phase_shift_2d(np.fft.fftshift(np.fft.fftn(s2)), 0, 0.5)
    s2_shift = np.fft.ifftn(np.fft.ifftshift(S2)).real

    S3 = phase_shift_2d(np.fft.fftshift(np.fft.fftn(s3)), 0.5, 0.0)
    s3_shift = np.fft.ifftn(np.fft.ifftshift(S3)).real

    S4 = phase_shift_2d(np.fft.fftshift(np.fft.fftn(s4)), 0.5, 0.5)
    s4_shift = np.fft.ifftn(np.fft.ifftshift(S4)).real

    r = image.shape[0]//2
    print("0", r)

    c1 = two_image_frc(s1, s2_shift, r)
    c2 = two_image_frc(s3_shift, s4_shift, r)

    print("1", s1.shape)
    print("2", s2.shape)
    print("3", s3.shape)
    print("4", s4.shape)
    print("5", c1.shape)
    print("6", c2.shape)

    c_avg = np.mean([c1, c2], axis=0)

    #c_avg = 2*c_avg / (1 + c_avg)

    #freq = get_radial_spatial_frequencies(s1, 2)

    #return freq, c_avg
    return np.arange(len(c_avg)), c_avg

def get_FSC_curve(vol1, vol2):
    r = vol1.shape[0]//2
    corrs = two_volume_fsc(vol1, vol2, r)
    freqs = get_radial_spatial_frequencies(vol1, 1)
    return freqs, corrs

def get_FRC_curve(img1, img2):
    r = img1.shape[0]//2
    corrs = two_image_fsc(img1, img2, r)
    freqs = get_radial_spatial_frequencies(img1, 1)
    return freqs, corrs
