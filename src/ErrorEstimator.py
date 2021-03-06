#!/usr/bin/env python3


import numpy as np
from scipy.interpolate import Rbf, LinearNDInterpolator, NearestNDInterpolator
import numdifftools as nd
from src.Meshing import *
from SimPEG.utils import surface2ind_topo
from src.Utils import *
from SimPEG import maps

try:
    from pymatsolver import Pardiso as Solver
except ImportError:
    from SimPEG import SolverLU as Solver


def interpolate_rbf(x, y, z, x_val, y_val, z_val):
    """Radial basis function interpolation.

    Parameters
    ----------
    x : np.ndarray
        x-faces or x-edges of a mesh
    y : np.ndarray
        y-faces or y-edges of a mesh
    z : np.ndarray
        z-faces or z-edges of a mesh
    x_val : np.ndarray
        curl values or electric field values in the x-direction
    y_val : np.ndarray
        curl values or electric field values in the y-direction
    z_val : np.ndarray
        curl values or electric field values in the z-direction

    Returns
    -------
    scipy.interpolate.rbf.Rbf
        a radial basis function interpolation object
    """
    x_interpolated = Rbf(x[:, 0], x[:, 1], x[:, 2], x_val)
    y_interpolated = Rbf(y[:, 0], y[:, 1], y[:, 2], y_val)
    z_interpolated = Rbf(z[:, 0], z[:, 1], z[:, 2], z_val)

    return x_interpolated, y_interpolated, z_interpolated


def interpolate_nearest(x, y, z, x_val, y_val, z_val):
    """Neirest neighbour interpolation.

    Parameters
    ----------
    x : np.ndarray
        x-faces or x-edges of a mesh
    y : np.ndarray
        y-faces or y-edges of a mesh
    z : np.ndarray
        z-faces or z-edges of a mesh
    x_val : np.ndarray
        curl values or electric field values in the x-direction
    y_val : np.ndarray
        curl values or electric field values in the y-direction
    z_val : np.ndarray
        curl values or electric field values in the z-direction

    Returns
    -------
    scipy.interpolate.ndgriddata.NearestNDInterpolator
        a neirest neighbour interpolation object
    """
    x_interpolated = NearestNDInterpolator(x, x_val)
    y_interpolated = NearestNDInterpolator(y, y_val)
    z_interpolated = NearestNDInterpolator(z, z_val)

    return x_interpolated, y_interpolated, z_interpolated


def interpolate_linear(x, y, z, x_val, y_val, z_val):
    """Linear interpolation.

    Parameters
    ----------
    x : np.ndarray
        x-faces or x-edges of a mesh
    y : np.ndarray
        y-faces or y-edges of a mesh
    z : np.ndarray
        z-faces or z-edges of a mesh
    x_val : np.ndarray
        curl values or electric field values in the x-direction
    y_val : np.ndarray
        curl values or electric field values in the y-direction
    z_val : np.ndarray
        curl values or electric field values in the z-direction

    Returns
    -------
    scipy.interpolate.interpnd.LinearNDInterpolator
        a linear interpolation object
    """

    x_interpolated = LinearNDInterpolator(x, x_val)
    y_interpolated = LinearNDInterpolator(y, y_val)
    z_interpolated = LinearNDInterpolator(z, z_val)

    return x_interpolated, y_interpolated, z_interpolated


def estimate_curl_electric_field(mesh, survey, model_map, model, interpolation='rbf', frequency=1.0,
                                 omega=2 * np.pi, parameter='resistivity'):
    """Interpolates the curl and the electric field values in the mesh."""

    x_faces = mesh.faces_x
    y_faces = mesh.faces_y
    z_faces = mesh.faces_z

    x_edges = mesh.edges_x
    y_edges = mesh.edges_y
    z_edges = mesh.edges_z

    # Solution by forward modelling for magnetic flux density and electric field
    if parameter == 'resistivity':
        simulation = fdem.simulation.Simulation3DMagneticFluxDensity(
            mesh, survey=survey, rhoMap=model_map, Solver=Solver
        )

        simulationelectricfield = fdem.simulation.Simulation3DElectricField(
            mesh, survey=survey, rhoMap=model_map, Solver=Solver
        )
    else:
        simulation = fdem.simulation.Simulation3DMagneticFluxDensity(
            mesh, survey=survey, sigmaMap=model_map, Solver=Solver
        )

        simulationelectricfield = fdem.simulation.Simulation3DElectricField(
            mesh, survey=survey, sigmaMap=model_map, Solver=Solver
        )

    # Compute magnetic flux density
    fields = simulation.fields(model)
    magnetic_flux_density = fields[:, 'bSolution']

    # Source field
    sources = simulation.getSourceTerm(frequency)
    Sm = sources[0]

    # Curl of Electric field computed on the cell faces
    curl = Sm - 1j * omega * magnetic_flux_density
    curl = np.reshape(curl, len(curl))

    x_curl = curl[0:mesh.n_faces_x]
    y_curl = curl[mesh.n_faces_x:mesh.n_faces_x + mesh.n_faces_y]
    z_curl = curl[mesh.n_faces_x + mesh.n_faces_y:mesh.n_faces_x + mesh.n_faces_y + mesh.n_faces_z]

    if interpolation == 'rbf':
        interpolator = interpolate_rbf
    elif interpolation == 'linear':
        interpolator = interpolate_linear
    else:
        interpolator = interpolate_nearest

    curl_x_inter, curl_y_inter, curl_z_inter = interpolator(x_faces, y_faces, z_faces, x_curl,
                                                            y_curl, z_curl)

    # Electric field solution
    fieldselectric = simulationelectricfield.fields(model)
    EF = fieldselectric[:, 'eSolution']
    EF = np.reshape(EF, len(EF))

    EF_x = EF[0:mesh.n_edges_x]
    EF_y = EF[mesh.n_edges_x:mesh.n_edges_x + mesh.n_edges_y]
    EF_z = EF[
           mesh.n_edges_x + mesh.n_edges_y:mesh.n_edges_x + mesh.n_edges_y + mesh.n_edges_z]

    EF_x_inter, EF_y_inter, EF_z_inter = interpolator(x_edges, y_edges, z_edges, EF_x, EF_y, EF_z)

    return curl_x_inter, curl_y_inter, curl_z_inter, EF_x_inter, EF_y_inter, EF_z_inter


def compute_cell_error(cell, curl_x, curl_y, curl_z, ef_x, ef_y, ef_z):
    """Computes the error in a given cell of a mesh"""

    def ef_interpolator(x):
        return np.array([ef_x(*x), ef_y(*x), ef_z(*x)])

    jacobian = nd.Jacobian(ef_interpolator, order=2)(cell)
    jacobian[np.isnan(jacobian)] = 0  # handle NaN-values in the jacobian
    curl = np.array([jacobian[2, 1] - jacobian[1, 2], jacobian[0, 2] -
                     jacobian[2, 0], jacobian[1, 0] - jacobian[0, 1]])

    curl_field = np.array([curl_x(*cell), curl_y(*cell), curl_z(*cell)])
    error = np.linalg.norm(curl_field - curl)
    return error


def estimate_error(search_area, curl_x, curl_y, curl_z
                   , ef_x, ef_y, ef_z,
                   refine_percentage=0.05):
    """Estimates the error in a predefined search area in a mesh"""

    cell_errors = []
    for cell in search_area:
        error = compute_cell_error(cell, curl_x, curl_y, curl_z, ef_x, ef_y, ef_z)
        cell_errors.append(error)

    np.save('error.npy', np.asarray(cell_errors))
    n_refine_cells = int(np.ceil(refine_percentage * len(search_area)))
    cells_to_refine = search_area[np.argpartition(cell_errors, -n_refine_cells)[-n_refine_cells:]]
    return cells_to_refine


def iterator(mesh, domain, surface, cell_width, objct, coordinates
             , receiver_locations, source_locations, survey, par_background, par_object,
             ind_object, frequency=1, omega=2 * np.pi
             , parameter='resistivity', interpolation='rbf', type_object='block'
             , lim_iterations=5, factor_object=2, factor_receiver=3, factor_source=3
             , refine_percentage=0.05, axis='x', degrees_rad=0, radius=1, Ex=None, Ey=None, Ez=None
             , diff_list=np.array([[0, 0]]), r_a_o_list=None, r_a_r_list=None, r_a_s_list=None):

    """An iteration scheme that implements an error estimator to adaptively refine
    a mesh, in order to reduce the error of the electric field solution.
    This function is mainly used for small objects in a domain.

    If you want to continue from previous iteration, you have to give the mesh, field values,
    convergence list and previous refinements as input arguments."""

    # Find cells that are active in the forward modeling (cells below surface)
    ind_active = surface2ind_topo(mesh, surface)

    # Define mapping from model to active cells
    model_map = maps.InjectActiveCells(mesh, ind_active, par_background)

    # Define model. Models in SimPEG are vector arrays
    model = par_background * np.ones(ind_active.sum())
    if type_object == 'block':
        ind_object = get_ind_block(mesh, ind_active, coordinates, axis, degrees_rad)
    if type_object == 'sphere':
        ind_object = get_ind_sphere(mesh, ind_active, coordinates, radius)

    model[ind_object] = par_object

    diff = 10
    if diff_list[0, 0] == 0:
        i = 0
        av_diff_list = []
        refine_at_object_list = []
        refine_at_receivers_list = []
        refine_at_sources_list = []
    # Starting after the pause
    else:
        i = diff_list[-1, 0]
        av_diff_list = list(diff_list)
        refine_at_object_list = r_a_o_list
        refine_at_receivers_list = r_a_r_list
        refine_at_sources_list = r_a_s_list
        lim_iterations = lim_iterations + i
        ef_old_x = Ex
        ef_old_y = Ey
        ef_old_z = Ez

    def ef_interpolator(x):
        return np.array([ef_x(*x), ef_y(*x), ef_z(*x)])

    def ef_old_interpolator(x):
        return np.array([ef_old_x(*x), ef_old_y(*x), ef_old_z(*x)])

    while diff > 0.01 and i < lim_iterations:
        # Maximum relative difference between current and previous iteration should fall below 1% in order to converge.

        # Define search areas
        search_area_obj = search_area_object(mesh, objct, factor=factor_object)
        search_area_receiv = search_area_receivers(mesh, receiver_locations,
                                                   factor=factor_receiver)
        search_area_sourc = search_area_sources(mesh, source_locations,
                                                factor=factor_source)
        # Interpolate curl and electric field
        curl_x, curl_y, curl_z, ef_x, ef_y, ef_z = estimate_curl_electric_field(mesh, survey,
                                                                                model_map,
                                                                                model,
                                                                                interpolation=interpolation,
                                                                                frequency=frequency,
                                                                                omega=omega
                                                                                ,
                                                                                parameter=parameter)
        # Compare electric field values until relative difference falls below 1%
        if diff_list[0, 0] == 0:
            if i > 0:
                relative_difference_Efield = []
                for cell in search_area_obj:
                    # This equation is sensitive to catastrophic failure
                    form = np.abs(
                        (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(
                            cell))
                    relative_difference_Efield.append(np.linalg.norm(form))
                for cell in search_area_receiv:
                    # This equation is sensitive to catastrophic failure
                    form = np.abs(
                        (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(
                            cell))
                    relative_difference_Efield.append(np.linalg.norm(form))
                for cell in search_area_sourc:
                    # This equation is sensitive to catastrophic failure
                    form = np.abs(
                        (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(
                            cell))
                    relative_difference_Efield.append(np.linalg.norm(form))

                diff = sum(relative_difference_Efield) / len(relative_difference_Efield)
                av_diff_list.append([i + 1, diff])
                print("Average relative difference is ", diff)
        else:
            relative_difference_Efield = []
            for cell in search_area_obj:
                # This equation is sensitive to catastrophic failure
                form = np.abs(
                    (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(cell))
                relative_difference_Efield.append(np.linalg.norm(form))
            for cell in search_area_receiv:
                # This equation is sensitive to catastrophic failure
                form = np.abs(
                    (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(cell))
                relative_difference_Efield.append(np.linalg.norm(form))
            for cell in search_area_sourc:
                # This equation is sensitive to catastrophic failure
                form = np.abs(
                    (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(cell))
                relative_difference_Efield.append(np.linalg.norm(form))

            diff = sum(relative_difference_Efield) / len(relative_difference_Efield)
            av_diff_list.append([i + 1, diff])
            print("Average relative difference is ", diff)

        ef_old_x = ef_x
        ef_old_y = ef_y
        ef_old_z = ef_z

        # Define cells to refine near object
        cells_to_refine_object = estimate_error(search_area_obj
                                                , curl_x, curl_y, curl_z
                                                , ef_x, ef_y, ef_z
                                                , refine_percentage=refine_percentage)
        refine_at_object_list.append(cells_to_refine_object)
        # Define cells to refine near receivers
        cells_to_refine_receivers = estimate_error(search_area_receiv
                                                   , curl_x, curl_y, curl_z
                                                   , ef_x, ef_y, ef_z
                                                   , refine_percentage=refine_percentage)
        refine_at_receivers_list.append(cells_to_refine_receivers)
        # Define cells to refine near sources
        cells_to_refine_sources = estimate_error(search_area_sourc
                                                 , curl_x, curl_y, curl_z
                                                 , ef_x, ef_y, ef_z
                                                 , refine_percentage=refine_percentage)
        refine_at_sources_list.append(cells_to_refine_sources)
        # Refine the mesh
        mesh = create_octree_mesh(domain, cell_width, objct, 'surface')
        refine_at_locations(mesh, source_locations)
        refine_at_locations(mesh, receiver_locations)
        for refo in refine_at_object_list:
            refine_at_locations(mesh, refo)
        for refr in refine_at_receivers_list:
            refine_at_locations(mesh, refr)
        for refs in refine_at_sources_list:
            refine_at_locations(mesh, refs)
        mesh.finalize()

        # Find cells that are active in the forward modeling (cells below surface)
        ind_active = surface2ind_topo(mesh, surface)

        # Define mapping from model to active cells
        model_map = maps.InjectActiveCells(mesh, ind_active, par_background)

        # Define model. Models in SimPEG are vector arrays
        model = par_background * np.ones(ind_active.sum())
        if type_object == 'block':
            ind_object = get_ind_block(mesh, ind_active, coordinates)
        if type_object == 'sphere':
            ind_object = get_ind_sphere(mesh, ind_active, coordinates, radius)

        model[ind_object] = par_object
        print(i)
        i += 1
    if diff < 0.01:
        return mesh, ef_x, ef_y, ef_z, np.array(av_diff_list)
    else:
        return mesh, ef_x, ef_y, ef_z, np.array(
            av_diff_list), refine_at_object_list, refine_at_receivers_list, refine_at_sources_list


def iteratornonobject(mesh, domain, cell_width, landscape, receiver_locations, source_locations,
                      survey,
                      resistivity_function, model_map, model, frequency=1, omega=2 * np.pi
                      , parameter='resistivity', interpolation='rbf'
                      , lim_iterations=5, factor_receiver=2, factor_source=2, factor_landscape=2,
                      refine_percentage=0.05, par_inactive=1e8
                      , Ex=None, Ey=None, Ez=None, diff_list=np.array([[0, 0]]), r_a_l_list=None,
                      r_a_r_list=None, r_a_s_list=None):
    """An iteration scheme that implements an error estimator to adaptively refine
    a mesh, in order to reduce the error of the electric field solution.
    This function is mainly used for large geophysical models.

    If you want to continue from previous iteration, you have to give the mesh, field values,
    convergence list and previous refinements as input arguments."""

    # Find cells that are active in the forward modeling (cells below surface)
    ind_active = np.array([True] * mesh.n_cells)

    # Define mapping from model to active cells
    model_map = maps.InjectActiveCells(mesh, ind_active, par_inactive)

    # Define model. Models in SimPEG are vector arrays
    model = resistivity_function(mesh.cell_centers)

    diff = 10
    i = 0
    if diff_list[0, 0] == 0:
        i = 0
        av_diff_list = []
        refine_at_landscape_list = []
        refine_at_receivers_list = []
        refine_at_sources_list = []
    # Starting after the pause
    else:
        i = diff_list[-1, 0]
        av_diff_list = list(diff_list)
        refine_at_landscape_list = r_a_l_list
        refine_at_receivers_list = r_a_r_list
        refine_at_sources_list = r_a_s_list
        lim_iterations = lim_iterations + i
        ef_old_x = Ex
        ef_old_y = Ey
        ef_old_z = Ez

    def ef_interpolator(x):
        return np.array([ef_x(*x), ef_y(*x), ef_z(*x)])

    def ef_old_interpolator(x):
        return np.array([ef_old_x(*x), ef_old_y(*x), ef_old_z(*x)])

    while diff > 0.01 and i < lim_iterations:
        # Maximum relative difference between current and previous iteration should fall below 1%
        # in order to converge.

        # Define search areas
        search_area_below_landscape = search_area_landscape(mesh, domain, landscape,
                                                            factor=factor_landscape)
        search_area_receiv = search_area_receivers(mesh, receiver_locations,
                                                   factor=factor_receiver)
        search_area_sourc = search_area_sources(mesh, source_locations,
                                                factor=factor_source)
        # Interpolate curl and electric field
        curl_x, curl_y, curl_z, ef_x, ef_y, ef_z = estimate_curl_electric_field(mesh, survey,
                                                                                model_map,
                                                                                model,
                                                                                interpolation=interpolation,
                                                                                frequency=frequency,
                                                                                omega=omega
                                                                                ,
                                                                                parameter=parameter)
        # Compare electric field values until relative difference falls below 1%
        if diff_list[0, 0] == 0:
            if i > 0:
                relative_difference_Efield = []
                for cell in search_area_below_landscape:
                    form = np.abs(
                        (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(
                            cell))
                    relative_difference_Efield.append(np.linalg.norm(form))
                for cell in search_area_receiv:
                    form = np.abs(
                        (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(
                            cell))
                    relative_difference_Efield.append(np.linalg.norm(form))
                for cell in search_area_sourc:
                    form = np.abs(
                        (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(
                            cell))
                    relative_difference_Efield.append(np.linalg.norm(form))

                diff = sum(relative_difference_Efield) / len(relative_difference_Efield)
                av_diff_list.append([i + 1, diff])
                print("Average relative difference is ", diff)
        else:
            relative_difference_Efield = []
            for cell in search_area_below_landscape:
                form = np.abs(
                    (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(cell))
                relative_difference_Efield.append(np.linalg.norm(form))
            for cell in search_area_receiv:
                form = np.abs(
                    (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(cell))
                relative_difference_Efield.append(np.linalg.norm(form))
            for cell in search_area_sourc:
                form = np.abs(
                    (ef_old_interpolator(cell) - ef_interpolator(cell)) / ef_old_interpolator(cell))
                relative_difference_Efield.append(np.linalg.norm(form))

            diff = sum(relative_difference_Efield) / len(relative_difference_Efield)
            av_diff_list.append([i + 1, diff])
            print("Average relative difference is ", diff)

        ef_old_x = ef_x
        ef_old_y = ef_y
        ef_old_z = ef_z

        # Define cells to refine near object
        cells_to_refine_landscape = estimate_error(search_area_below_landscape
                                                   , curl_x, curl_y, curl_z
                                                   , ef_x, ef_y, ef_z
                                                   , refine_percentage=refine_percentage)
        refine_at_landscape_list.append(cells_to_refine_landscape)

        # Define cells to refine near receivers
        cells_to_refine_receivers = estimate_error(search_area_receiv
                                                   , curl_x, curl_y, curl_z
                                                   , ef_x, ef_y, ef_z
                                                   , refine_percentage=refine_percentage)
        refine_at_receivers_list.append(cells_to_refine_receivers)

        # Define cells to refine near sources
        cells_to_refine_sources = estimate_error(search_area_sourc
                                                 , curl_x, curl_y, curl_z
                                                 , ef_x, ef_y, ef_z
                                                 , refine_percentage=refine_percentage)
        refine_at_sources_list.append(cells_to_refine_sources)

        # Refine the mesh
        mesh = create_octree_mesh(domain, cell_width, landscape, 'surface')
        refine_at_locations(mesh, source_locations)
        refine_at_locations(mesh, receiver_locations)
        for refo in refine_at_landscape_list:
            refine_at_locations(mesh, refo)
        for refr in refine_at_receivers_list:
            refine_at_locations(mesh, refr)
        for refs in refine_at_sources_list:
            refine_at_locations(mesh, refs)
        mesh.finalize()

        # Find cells that are active in the forward modeling (cells below surface)
        ind_active = np.array([True] * mesh.n_cells)

        # Define mapping from model to active cells
        model_map = maps.InjectActiveCells(mesh, ind_active, par_inactive)

        # Define model. Models in SimPEG are vector arrays
        model = resistivity_function(mesh.cell_centers)
        print("Iteration: ", i)
        i += 1
    if diff < 0.01:
        return mesh, ef_x, ef_y, ef_z, np.array(av_diff_list)
    else:
        return mesh, ef_x, ef_y, ef_z, np.array(
            av_diff_list), refine_at_landscape_list, refine_at_receivers_list, refine_at_sources_list
