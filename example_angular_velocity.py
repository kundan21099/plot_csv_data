# paste this into a python notebook (no internet needed)
import numpy as np
import matplotlib.pyplot as plt

# Example data: replace these arrays with your sensor logs
times = np.array([0.0, 0.1, 0.2])
wx = np.array([0.10, 0.20, 0.15])  # rad/s
wy = np.array([0.00, 0.05, 0.10])
wz = np.array([0.00, 0.00, 0.00])

# 1) magnitude
w_mag = np.sqrt(wx**2 + wy**2 + wz**2)

# 2) integrate each component to get angle (trapezoidal integration)
angle_x = np.zeros_like(wx)
angle_y = np.zeros_like(wy)
angle_z = np.zeros_like(wz)
for i in range(1, len(times)):
    dt = times[i] - times[i-1]
    angle_x[i] = angle_x[i-1] + 0.5*(wx[i-1] + wx[i])*dt
    angle_y[i] = angle_y[i-1] + 0.5*(wy[i-1] + wy[i])*dt
    angle_z[i] = angle_z[i-1] + 0.5*(wz[i-1] + wz[i])*dt

angle_mag = np.sqrt(angle_x**2 + angle_y**2 + angle_z**2)

# 3) plots
plt.figure(figsize=(10,6))

plt.subplot(3,1,1)
plt.plot(times, wx, label='ωx'); plt.plot(times, wy, '--', label='ωy'); plt.plot(times, wz, ':', label='ωz')
plt.ylabel('ω (rad/s)'); plt.legend(); plt.grid(True)

plt.subplot(3,1,2)
plt.plot(times, w_mag, label='|ω|')
plt.ylabel('angular speed (rad/s)'); plt.legend(); plt.grid(True)

plt.subplot(3,1,3)
plt.plot(times, angle_x, label='angle_x'); plt.plot(times, angle_y, '--', label='angle_y')
plt.plot(times, angle_z, ':', label='angle_z'); plt.plot(times, angle_mag, '-.', label='angle_mag')
plt.xlabel('time (s)'); plt.ylabel('angle (rad)'); plt.legend(); plt.grid(True)

plt.tight_layout()
plt.show()
