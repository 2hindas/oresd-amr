#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Dec  9 11:26:41 2020

@author: larslaheij
"""
import emg3d
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from discretize import TreeMesh
from discretize.utils import mkvc, refine_tree_xyz
from scipy.spatial.transform import Rotation as R
from SimPEG.utils import plot2Ddata, surface2ind_topo
import SimPEG
from SimPEG import maps
import SimPEG.electromagnetics.frequency_domain as fdem
import os
import matplotlib as mpl
import matplotlib.pyplot as plt
import scipy as sp
import numdifftools as nd

try:
    from pymatsolver import Pardiso as Solver
except ImportError:
    from SimPEG import SolverLU as Solver

#Surface Definition
domain= ((-500, 4500), (-1000, 1000), (-1200, 200))
xx, yy = np.meshgrid(np.linspace(-500, 4500, 101), np.linspace(-1000, 1000, 101))
zz = np.zeros(np.shape(xx))
topo_xyz = np.c_[mkvc(xx), mkvc(yy), mkvc(zz)] #Surface

src = [0, 0, 0, 0, 0]        # x-dir. source at the origin, 50 m above seafloor
off = np.arange(20, 41)*100  # Offsets
rec = [off, off*0, 0]        # In-line receivers on the seafloor

# Defining transmitter location
xtx, ytx, ztx = np.meshgrid([0], [0], [0])
source_locations = np.c_[mkvc(xtx), mkvc(ytx), mkvc(ztx)]
ntx = np.size(xtx)
print("Number of transmitters",len(source_locations))

# Define receiver locations
N = 21
xrx, yrx, zrx = np.meshgrid(np.linspace(2000, 4000, N), [0], [0])
receiver_locations = np.c_[mkvc(xrx), mkvc(yrx), mkvc(zrx)]
frequencies = [1.0]                   # Frequency (Hz)
omegas = [2.0*np.pi]                  # Radial frequency (Hz)
source_list = []  # Create empty list to store sources
print("Number of receivers",len(receiver_locations))

# Each unique location and frequency defines a new transmitter
for ii in range(len(frequencies)):
    for jj in range(ntx):

        # Define receivers of different type at each location
        bzr_receiver = fdem.receivers.PointMagneticFluxDensitySecondary(
            receiver_locations[jj, :], "z", "real"
        )
        bzi_receiver = fdem.receivers.PointMagneticFluxDensitySecondary(
            receiver_locations[jj, :], "z", "imag"
        )
        receivers_list = [bzr_receiver, bzi_receiver]

        # Must define the transmitter properties and associated receivers
        source_list.append(
            fdem.sources.MagDipole(
                receivers_list,
                frequencies[ii],
                source_locations[jj],
                orientation="z",
                moment=1,
            )
        )
survey = fdem.Survey(source_list)

# minimum cell width in each dimension
dx = 100
dy = 100
dz = 100

# domain dimensions
x_length = np.abs(domain[0][0] - domain[0][1]) 
y_length = np.abs(domain[1][0] - domain[1][1]) 
z_length = np.abs(domain[2][0] - domain[2][1]) 

# number of cells necessary in each dimension
nbx = 2 ** int(np.round(np.log(x_length / dx) / np.log(2.0)))
nby = 2 ** int(np.round(np.log(y_length / dy) / np.log(2.0)))
nbz = 2 ** int(np.round(np.log(z_length / dz) / np.log(2.0)))

# Define base mesh (domain and finest discretization)
hx = [(dx,nbx)]
hy = [(dy,nby)]
hz = [(dz,nbz)]
mesh = TreeMesh([hx, hy, hz], origin=[-500,-1000,-1200])

# Define rotation matrix
# 10 degrees rotation around the x-axis
#rotation = R.from_euler('x', 10, degrees=True).as_matrix()

# Define inner points for rectangular box
x = np.linspace(0, 4000, 30)
y = np.linspace(-500, 500, 30)
z = np.linspace(-1200, -1000, 30)
xp, yp, zp = np.meshgrid(x, y, z)
xyz = np.c_[mkvc(xp), mkvc(yp), mkvc(zp)]

# Mesh refinement based on topography
mesh = refine_tree_xyz(
    mesh, topo_xyz, octree_levels=[0, 0, 0, 1], method="surface", finalize=False
)
# Mesh refinement near transmitters and receivers
mesh = refine_tree_xyz(
    mesh, source_locations, octree_levels=[2, 4], method="radial", finalize=False
)

mesh = refine_tree_xyz(
    mesh, receiver_locations, octree_levels=[2, 4], method="radial", finalize=False
)
'''
# Mesh refinement at block location
mesh = refine_tree_xyz(mesh, xyz, octree_levels=[0, 2, 4], method="box", finalize=False)
'''
mesh.finalize()
# The total number of cells
nC = mesh.nC
print("Total number of cells", nC)

Cellfaces = mesh.n_faces
print("Total number of cell faces", Cellfaces)

Celledges = mesh.n_edges
print("Total number of cell edges", Celledges)


xyzcells = mesh.cell_centers
xcells = xyzcells[:,0] #Cell centers in x-direction
ycells = xyzcells[:,1] #Cell centers in y-direction
zcells = xyzcells[:,2] #Cell centers in z-direction

xedges = mesh.edges_x # x-edges
yedges = mesh.edges_y # y-edges
zedges = mesh.edges_z # z-edges

xfaces = mesh.faces_x # x-faces
yfaces = mesh.faces_y # y-faces
zfaces = mesh.faces_z # z-faces

# Resistivity in Ohm m)
res_background = 1.0
res_block = 100.0
conductivity_background = 1/100.0
conductivity_block = 1/1.0

# Find cells that are active in the forward modeling (cells below surface)
ind_active = surface2ind_topo(mesh, topo_xyz)

# Define mapping from model to active cells
model_map = maps.InjectActiveCells(mesh, ind_active, res_background)

# Define model. Models in SimPEG are vector arrays
model = res_background * np.ones(ind_active.sum())
ind_block = (
    (mesh.gridCC[ind_active, 0] <= 4000.0)
    & (mesh.gridCC[ind_active, 0] >= 0.0)
    & (mesh.gridCC[ind_active, 1] <= 500.0)
    & (mesh.gridCC[ind_active, 1] >= -500.0)
    & (mesh.gridCC[ind_active, 2] <= -1000.0)
    & (mesh.gridCC[ind_active, 2] >= -1200.0)
)
model[ind_block] = res_block
'''
# Plot cell volumes
v = mesh.cell_volumes
mesh.plot_slice(np.log10(v),ind = 1,grid=True)
plt.show()
'''
#-----------------------------------------------------------------------------
#This part of the code is relevant as error estimator indicator
#Solution
simulation = fdem.simulation.Simulation3DMagneticFluxDensity(
    mesh, survey=survey, rhoMap=model_map, Solver=Solver
)

simulationelectricfield = fdem.simulation.Simulation3DElectricField(
    mesh, survey=survey, rhoMap=model_map, Solver=Solver
)
#Compute magnetic flux density
fields = simulation.fields(model)
MagFluxDensity = fields[:, 'bSolution'] #Field of the magnetic flux density
print("Length of flux array",len(MagFluxDensity))
print("Fluxes are computed at the cell faces.")

#Source field
sources = simulation.getSourceTerm(frequencies[0])
Sm = sources[0] 
print("Length of Sm is",len(Sm))

#Curl of Electric field computed on the cell faces
print("Curl of Electric field computed on the cell faces has formula Ce = Sm -i*omega*b. ")
Ce = Sm - 1j*omegas[0]*MagFluxDensity #Curl electric field

#Electric field solution
fieldselectric = simulationelectricfield.fields(model)
Electricfield = fieldselectric[:,'eSolution']
CeFromEfield = mesh.edge_curl*Electricfield


#From face to cell center operator
A = mesh.average_face_to_cell
CeCell1 = A*Ce
CeCell1 = np.reshape(CeCell1,len(CeCell1))
CeCell2 = A*CeFromEfield
CeCell2 = np.reshape(CeCell2,len(CeCell2))
#Compute error in every cell center
errorcellcenters = []
for i in range(len(xyzcells)):
    errorcellcenters.append(np.abs(CeCell1[i]-CeCell2[i]))
                            
percentage = 0.05 #Percentage of the grid you want to refine
Ncellstorefine = int(np.ceil(percentage*len(xyzcells)))
cellstorefine = xyzcells[np.argpartition(errorcellcenters,-Ncellstorefine)[-Ncellstorefine:]]
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.scatter(cellstorefine[:,0], cellstorefine[:,1], cellstorefine[:,2])
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')

plt.show()
#-----------------------------------------------------------------------------
print('Error estimator is af')