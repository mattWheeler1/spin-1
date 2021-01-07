import numpy as np
import h5py
import cupy as cp
import include.phaseImprinting

"""Turbulence simulation for a scalar BEC. Vortices are generated by via phase imprinting."""

# --------------------------------------------------------------------------------------------------------------------
# Controlled variables:
# --------------------------------------------------------------------------------------------------------------------
Nx, Ny = 1024, 1024
Mx, My = Nx // 2, Ny // 2  # Number of grid pts
dx = dy = 1  # Grid spacing
dkx = np.pi / (Mx * dx)
dky = np.pi / (My * dy)  # K-space spacing
len_x = Nx * dx  # Box length
len_y = Ny * dy
x = cp.arange(-Mx, Mx) * dx
y = cp.arange(-My, My) * dy
X, Y = cp.meshgrid(x, y)  # Spatial meshgrid

# k-space arrays and meshgrid:
kx = cp.fft.fftshift(cp.arange(-Mx, Mx) * dkx)
ky = cp.fft.fftshift(cp.arange(-My, My) * dky)
Kx, Ky = cp.meshgrid(kx, ky)  # K-space meshgrid

# Controlled variables
V = 0.  # Doubly periodic box
c0 = 3e-5

# Time steps, number and wavefunction save variables
Nt = 10000000
Nframe = 10000   # Save data every Nframe number of timesteps
dt = 1e-2  # Imaginary time timestep
t = 0.
k = 0   # Array index

filename = 'scalar_imp'    # Name of file to save data to
data_path = '../scratch/data/scalar/{}.hdf5'.format(filename)
backup_data_path = '../scratch/data/scalar/{}_backup.hdf5'.format(filename)

fresh_simulation = True  # Boolean that corresponds to a fresh simulation if True or a continued simulation if False

# --------------------------------------------------------------------------------------------------------------------
# Generating initial state:
# --------------------------------------------------------------------------------------------------------------------
# If it is a continued simulation, load the previous data and continue to evolution:
if not fresh_simulation:
    previous_data = h5py.File(backup_data_path, 'r')
    psi_k = cp.array(previous_data['wavefunction/psi_k'])
    t = np.round(previous_data['time'][...])
    k = previous_data['array_index'][...]
    previous_data.close()

# If it is a fresh simulation, generate the initial state:
else:
    n_0 = 1.6e9 / 1024 ** 2

    # Generate phase:
    N_vort = 1000
    xi = 1 / np.sqrt(2 * n_0 * c0)  # Healing length
    vort_pos = include.phaseImprinting.get_positions(N_vort, 5 * xi, len_x, len_y)  # Generator of vortex positions

    theta = include.phaseImprinting.get_phase(N_vort, vort_pos, Nx, Ny, X, Y, len_x, len_y)

    # Construct wavefunction:
    psi = cp.sqrt(n_0) * cp.exp(1j * theta)
    psi_k = cp.fft.fft2(psi)
    atom_num = dx * dy * cp.sum(cp.abs(cp.fft.ifft2(psi_k)) ** 2)
    theta_fix = np.angle(psi)

    # ------------------------------------------------------------------------------------------------------------------
    # Imaginary time evolution
    # ------------------------------------------------------------------------------------------------------------------
    for i in range(500):
        # Kinetic energy:
        psi_k *= cp.exp(-0.25 * dt * (Kx ** 2 + Ky ** 2))

        # Backward FFT:
        psi = cp.fft.ifft2(psi_k)

        # Interaction term:
        psi *= cp.exp(-dt * (c0 * cp.abs(psi) ** 2))

        # Forward FFT:
        psi_k = cp.fft.fft2(psi)

        # Kinetic energy:
        psi_k *= cp.exp(-0.25 * dt * (Kx ** 2 + Ky ** 2))

        # Re-normalising:
        atom_num_new = dx * dy * cp.sum(cp.abs(cp.fft.ifft2(psi_k)) ** 2)
        psi_k = cp.fft.fft2(cp.sqrt(atom_num) * cp.fft.ifft2(psi_k) / cp.sqrt(atom_num_new))

        # Fixing phase:
        psi = cp.fft.ifft2(psi_k)
        psi *= cp.exp(1j * theta_fix) / cp.exp(1j * cp.angle(psi))
        psi_k = cp.fft.fft2(psi)

    # Creating file to save to:
    with h5py.File(data_path, 'w') as data:
        # Saving spatial data:
        data.create_dataset('grid/x', x.shape, data=cp.asnumpy(x))
        data.create_dataset('grid/y', y.shape, data=cp.asnumpy(y))

        # Saving time variables:
        data.create_dataset('time/Nt', data=Nt)
        data.create_dataset('time/dt', data=dt)
        data.create_dataset('time/Nframe', data=Nframe)

        # Creating empty wavefunction datasets to store data:
        data.create_dataset('wavefunction/psi', (Nx, Ny, 1), maxshape=(Nx, Ny, None), dtype='complex64')

        # Stores initial state:
        data.create_dataset('initial_state/psi', data=cp.asnumpy(cp.fft.ifft2(psi_k)))

# ---------------------------------------------------------------------------------------------------------------------
# Real time evolution
# ---------------------------------------------------------------------------------------------------------------------
for i in range(Nt):

    # Kinetic energy:
    psi_k *= cp.exp(-0.25 * 1j * dt * (Kx ** 2 + Ky ** 2))

    # Backward FFT:
    psi = cp.fft.ifft2(psi_k)

    # Interaction term:
    psi *= cp.exp(-1j * dt * (c0 * cp.abs(psi) ** 2))

    # Forward FFT:
    psi_k = cp.fft.fft2(psi)

    # Kinetic energy:
    psi_k *= cp.exp(-0.25 * 1j * dt * (Kx ** 2 + Ky ** 2))

    # Saves data
    if np.mod(i + 1, Nframe) == 0:
        with h5py.File(data_path, 'r+') as data:
            new_psi = data['wavefunction/psi']
            new_psi.resize((Nx, Ny, k + 1))
            new_psi[:, :, k] = cp.asnumpy(cp.fft.ifft2(psi_k))
        k += 1

    # Saves 'backup' wavefunction we can use to continue simulations if ended:
    if np.mod(i + 1, 50000) == 0:
        with h5py.File(backup_data_path, 'w') as backup:
            backup.create_dataset('time', data=t)
            backup.create_dataset('wavefunction/psi_k', shape=psi_k.shape, dtype='complex64', data=cp.asnumpy(psi_k))
            backup.create_dataset('array_index', data=k)

    # Prints current time
    if np.mod(i, Nframe) == 0:
        print('t = %1.4f' % t)

    t += dt
