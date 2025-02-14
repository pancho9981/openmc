"""Dedicated module containing depletion function

Provided to avoid some circular imports
"""
from itertools import repeat, starmap
from multiprocessing import Pool
from scipy.sparse import bmat
import numpy as np


# Configurable switch that enables / disables the use of
# multiprocessing routines during depletion
USE_MULTIPROCESSING = True

# Allow user to override the number of worker processes to use for depletion
# calculations
NUM_PROCESSES = None


def deplete(func, chain, x, rates, dt, matrix_func=None, transfer_rates=None,
            *matrix_args):
    """Deplete materials using given reaction rates for a specified time

    Parameters
    ----------
    func : callable
        Function to use to get new compositions. Expected to have the
        signature ``func(A, n0, t) -> n1``
    chain : openmc.deplete.Chain
        Depletion chain
    x : list of numpy.ndarray
        Atom number vectors for each material
    rates : openmc.deplete.ReactionRates
        Reaction rates (from transport operator)
    dt : float
        Time in [s] to deplete for
    maxtrix_func : callable, optional
        Function to form the depletion matrix after calling
        ``matrix_func(chain, rates, fission_yields)``, where
        ``fission_yields = {parent: {product: yield_frac}}``
        Expected to return the depletion matrix required by
        ``func``
    transfer_rates : openmc.deplete.TransferRates, Optional
        Object to perform continuous reprocessing.

        .. versionadded:: 0.13.4
    matrix_args: Any, optional
        Additional arguments passed to matrix_func

    Returns
    -------
    x_result : list of numpy.ndarray
        Updated atom number vectors for each material

    """

    fission_yields = chain.fission_yields
    if len(fission_yields) == 1:
        fission_yields = repeat(fission_yields[0])
    elif len(fission_yields) != len(x):
        raise ValueError(
            "Number of material fission yield distributions {} is not "
            "equal to the number of compositions {}".format(
                len(fission_yields), len(x)))

    if matrix_func is None:
        matrices = map(chain.form_matrix, rates, fission_yields)
    else:
        matrices = map(matrix_func, repeat(chain), rates, fission_yields,
                       *matrix_args)

    if transfer_rates is not None:
        # Calculate transfer rate terms as diagonal matrices
        transfers = map(chain.form_rr_term, repeat(transfer_rates),
                        transfer_rates.burnable_mats)
        # Subtract transfer rate terms from Bateman matrices
        matrices = [matrix - transfer for (matrix, transfer) in zip(matrices,
                                                                    transfers)]

        if len(transfer_rates.index_transfer) > 0:
            # Calculate transfer rate terms as diagonal matrices
            transfer_pair = {
                mat_pair: chain.form_rr_term(transfer_rates, mat_pair)
                for mat_pair in transfer_rates.index_transfer
            }

            # Combine all matrices together in a single matrix of matrices
            # to be solved in one go
            n_rows = n_cols = len(transfer_rates.burnable_mats)
            rows = []
            for row in range(n_rows):
                cols = []
                for col in range(n_cols):
                    mat_pair = (transfer_rates.burnable_mats[row],
                                transfer_rates.burnable_mats[col])
                    if row == col:
                        # Fill the diagonals with the Bateman matrices
                        cols.append(matrices[row])
                    elif mat_pair in transfer_rates.index_transfer:
                        # Fill the off-diagonals with the transfer pair matrices
                        cols.append(transfer_pair[mat_pair])
                    else:
                        cols.append(None)

                rows.append(cols)
            matrix = bmat(rows)

            # Concatenate vectors of nuclides in one
            x_multi = np.concatenate([xx for xx in x])
            x_result = func(matrix, x_multi, dt)

            # Split back the nuclide vector result into the original form
            x_result = np.split(x_result, np.cumsum([len(i) for i in x])[:-1])

            return x_result

    inputs = zip(matrices, x, repeat(dt))

    if USE_MULTIPROCESSING:
        with Pool(NUM_PROCESSES) as pool:
            x_result = list(pool.starmap(func, inputs))
    else:
        x_result = list(starmap(func, inputs))

    return x_result
