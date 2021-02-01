#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3. Simulation
=============

The easiest way to model CSEM data for a survey is to make use of the Survey
and Simulation classes, :class:`emg3d.surveys.Survey` and
:class:`emg3d.simulations.Simulation`, respectively, together with the
automatic gridding functionality.

For this example we use the resistivity model created in the example
:ref:`sphx_glr_gallery_interactions_gempy-ii.py`.

"""
import os
import emg3d
import requests
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from scipy.interpolate import RectBivariateSpline
plt.style.use('ggplot')

###############################################################################
# Load Model
# ----------

fname = 'GemPy-II.h5'
if not os.path.isfile(fname):
    url = ("https://github.com/emsig/emg3d-gallery/blob/master/examples/"
           f"data/models/{fname}?raw=true")
    with open(fname, 'wb') as f:
        t = requests.get(url)
        f.write(t.content)

data = emg3d.load(fname)
model, mesh = data['model'], data['mesh']


###############################################################################
# Let's check the model

print(model)


###############################################################################
# So it is an isotropic model defined in terms of resistivities. Let's check
# the mesh

print(mesh)


###############################################################################
# Define the survey
# -----------------
#
# If you have actual field data then this info would normally come from a data
# file or similar. Here we create our own dummy survey, and later will create
# synthetic data for it.
#
# A **Survey** instance contains all survey-related information, hence source
# and receiver positions and measured data. See the relevant documentation for
# more details: :class:`emg3d.surveys.Survey`.
#
#
# Extract seafloor to simulate source and receiver depths
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''
#
# To create a realistic survey we create a small routine that finds the
# seafloor, so we can place receivers on the seafloor and sources 50 m above
# it. We use the fact that the seawater has resistivity of 0.3 Ohm.m in the
# model, and is the lowest value.

seafloor = np.ones((mesh.shape_cells[0], mesh.shape_cells[1]))
for i in range(mesh.shape_cells[0]):
    for ii in range(mesh.shape_cells[1]):
        # We take the seafloor to be the first cell which resistivity
        # is below 0.33
        seafloor[i, ii] = mesh.nodes_z[:-1][
                model.property_x[i, ii, :] < 0.33][0]

# Create a 2D interpolation function from it
bathymetry = RectBivariateSpline(
        mesh.cell_centers_x, mesh.cell_centers_y, seafloor)

###############################################################################
# Source and receiver positions
# '''''''''''''''''''''''''''''
#
# Sources and receivers can be defined in a few different ways. One way is by
# providing coordinates, where two coordinate formats are accepted:
#
# - ``(x0, x1, y0, y1, z0, z1)``: finite length dipole,
# - ``(x, y, z, azimuth, dip)``: point dipole,
#
# where the angles (azimuth and dip) are in degrees. For the coordinate system
# see `coordinate_system
# <https://empymod.readthedocs.io/en/stable/examples/coordinate_system.html>`_.
#
# A survey can contain electric and magnetic receivers, arbitrarily rotated.
# However, the ``Simulation`` is currently limited to electric receivers.
#
# Note that the survey just knows about the sources, receivers, frequencies,
# and observed data - it does not know anything of an underlying model.

# Angles for horizontal, x-directed Ex point dipoles
dip = 0.0
azimuth = 0.0

# Acquisition source frequencies (Hz)
frequencies = [1.0] #only use one frequency #frequencies = [0.5, 1.0]

# Source coordinates
src_x = 2*5000 # only use the middle source #np.arange(1, 4)*5000
src_y = 7500
# Source depths: 50 m above seafloor
src_z = bathymetry(src_x, src_y).ravel()+50
src = (src_x, src_y, src_z, dip, azimuth)

# Receiver positions
rec_x = np.arange(3, 18)*1e3
rec_y = 1e3+6500 #only use middle line of receivers #np.arange(3)*1e3+6500
RX, RY = np.meshgrid(rec_x, rec_y, indexing='ij')
RZ = bathymetry(rec_x, rec_y)
rec = (RX.ravel(), RY.ravel(), RZ.ravel(), dip, azimuth)


###############################################################################
# Create Survey
# '''''''''''''
#
# If you have observed data you can provide them, here we will create synthetic
# data later on. What you have to define is the expected noise floor and
# relative error, which is used to compute the misfit later on. Alternatively
# you can provide directly the standard deviation; see
# :class:`emg3d.surveys.Survey`.

survey = emg3d.surveys.Survey(
    name='GemPy-II Survey A',  # Name of the survey
    sources=src,               # Source coordinates
    receivers=rec,             # Receiver coordinates
    frequencies=frequencies,   # Two frequencies
    # data=data,               # If you have observed data
    noise_floor=1e-15,
    relative_error=0.05,
)

# Let's have a look at the survey:
print(survey)


###############################################################################
# Our survey has our sources and receivers and initiated a variable
# ``observed``, with NaN's. Each source and receiver got a name assigned. If
# you prefer other names you would have to define the sources and receivers
# through ``emg3d.surveys.Dipole``, and provide a list of dipoles to the survey
# instead of only a tuple of coordinates.
#
# We can also look at a particular source or receiver, e.g.,

print(survey.sources['Tx0'])


###############################################################################
# Which shows you all you need to know about a particular dipole: name, type
# (electric or magnetic), coordinates of its center, angles, and length.
#
# QC model and survey
# -------------------
'''
mesh.plot_3d_slicer(model.property_x, xslice=12000, yslice=7000,
                    pcolor_opts={'norm': LogNorm(vmin=0.3, vmax=200)})

# Plot survey in figure above
fig = plt.gcf()
fig.suptitle('Resistivity model (Ohm.m) and survey layout')
axs = fig.get_children()
axs[1].plot(survey.rec_coords[0], survey.rec_coords[1], 'bv')
axs[2].plot(survey.rec_coords[0], survey.rec_coords[2], 'bv')
axs[3].plot(survey.rec_coords[2], survey.rec_coords[1], 'bv')
axs[1].plot(survey.src_coords[0], survey.src_coords[1], 'r*')
axs[2].plot(survey.src_coords[0], survey.src_coords[2], 'r*')
axs[3].plot(survey.src_coords[2], survey.src_coords[1], 'r*')
plt.show()
'''
###############################################################################
# Create a Simulation (to compute 'observed' data)
# ------------------------------------------------
#
# The simulation class combines a model with a survey, and can compute
# synthetic data for it.
#
# Automatic gridding
# ''''''''''''''''''
#
# We use the automatic gridding feature implemented in the simulation class to
# use source- and frequency- dependent grids for the computation.
# Consult the following docs for more information:
#
# - `gridding_opts` in :class:`emg3d.simulations.Simulation`;
# - :func:`emg3d.simulations.estimate_gridding_opts`; and
# - :func:`emg3d.meshes.construct_mesh`.

gopts = {
    'properties': [0.3, 10, 1., 0.3],
    'min_width_limits': (100, 100, 50),
    'stretching': (None, None, [1.05, 1.5]),
    'domain': (
        [survey.rec_coords[0].min()-100, survey.rec_coords[0].max()+100],
        [survey.rec_coords[1].min()-100, survey.rec_coords[1].max()+100],
        [-5500, -1000]
    ),
}


###############################################################################
# Now we can initiate the simulation class and QC it:

simulation = emg3d.simulations.Simulation(
    name="True Model",    # A name for this simulation
    survey=survey,        # Our survey instance
    grid=mesh,            # The model mesh
    model=model,          # The model
    gridding='both',      # Frequency- and source-dependent meshes
    max_workers=4,        # How many parallel jobs
    # solver_opts,        # Any parameter to pass to emg3d.solve
    gridding_opts=gopts,  # Gridding options
)

# Let's QC our Simulation instance
###############################################################################
# Compute the data
# ''''''''''''''''
#
# We pass here the argument ``observed=True``; this way, the synthetic data is
# stored in our Survey as ``observed`` data, otherwise it would be stored as
# ``synthetic``. This is important later for optimization. It also adds
# Gaussian noise according to the noise floor and relative error we defined in
# the survey. By setting a minimum offset the receivers close to the source are
# switched off.
#
# This computes all results in parallel; in this case six models, three sources
# times two frequencies. You can change the number of workers at any time by
# setting ``simulation.max_workers``.
simulation.compute(observed=True, min_offset=500)

###############################################################################
# A ``Simulation`` has a few convenience functions, e.g.:
#
# - ``simulation.get_efield('Tx1', 0.5)``: Returns the electric field of the
#   entire domain for source ``'Tx1'`` and frequency 0.5 Hz.
# - ``simulation.get_hfield``; ``simulation.get_sfield``: Similar functions to
#   retrieve the magnetic fields and the source fields.
# - ``simulation.get_model``; ``simulation.get_grid``: Similar functions to
#   retrieve the computational grid and the model for a given source and
#   frequency.
#
# When we now look at our survey we see that the observed data variable is
# filled with the responses at the receiver locations. Note that the
# ``synthetic`` data is the actual computed data, the ``observed`` data, on the
# other hand, has Gaussian noise added and is set to NaN's for positions too
# close to the source.
###############################################################################
# QC Data
# -------
Efield =simulation.get_efield('Tx0', 1.0)

comp_mesh = simulation.get_grid('Tx0', 1.0)

xedges = comp_mesh.edges_x
yedges = comp_mesh.edges_y
zedges = comp_mesh.edges_z

Ex_inter = Efield[0:len(xedges)] #x-component of the electric field on the x-edges
Ey_inter = Efield[len(xedges):len(xedges) + len(yedges)] #y-component of the electric field on the y-edges
Ez_inter = Efield[
           len(xedges) + len(yedges):len(xedges) + len(yedges) + len(zedges)] #z-component of the electric field on the z-edges

xsearch = np.where((xedges[:,0]>=0) & (xedges[:,0]<=20000) & (xedges[:,1]>=0) & (xedges[:,1]<=20000) & (xedges[:,2]>=-7000) & (xedges[:,2]<=500))
ysearch = np.where((yedges[:,0]>=0) & (yedges[:,0]<=20000) & (yedges[:,1]>=0) & (yedges[:,1]<=20000) & (yedges[:,2]>=-7000) & (yedges[:,2]<=500))
zsearch = np.where((zedges[:,0]>=0) & (zedges[:,0]<=20000) & (zedges[:,1]>=0) & (zedges[:,1]<=20000) & (zedges[:,2]>=-7000) & (zedges[:,2]<=500))

Ex = np.take(Ex_inter,xsearch[0])
Ey = np.take(Ey_inter,ysearch[0])
Ez = np.take(Ez_inter,zsearch[0])

xedges = xedges[(xedges[:,0]>=0) & (xedges[:,0]<=20000) & (xedges[:,1]>=0) & (xedges[:,1]<=20000) & (xedges[:,2]>=-7000) & (xedges[:,2]<=500)]
yedges = yedges[(yedges[:,0]>=0) & (yedges[:,0]<=20000) & (yedges[:,1]>=0) & (yedges[:,1]<=20000) & (yedges[:,2]>=-7000) & (yedges[:,2]<=500)]
zedges = zedges[(zedges[:,0]>=0) & (zedges[:,0]<=20000) & (zedges[:,1]>=0) & (zedges[:,1]<=20000) & (zedges[:,2]>=-7000) & (zedges[:,2]<=500)]