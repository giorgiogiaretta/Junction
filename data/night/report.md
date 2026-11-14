# Night report (elapsed 5.1 h, 184 trials, device cuda)

## Square policy (best = most corners reached in closed loop, then lowest final error): 62 trials
- {'pos_mae_cm': 1.837708830833435, 'vel_base_cm': 4.453004360198975, 'corners_reached': 2.0, 'final_err_cm': 12.028749856884613} | {'hid': 256, 'layers': 3, 'h': 8, 'sigma': 0.04, 'reps': 3, 'epochs': 300, 'lr': 0.001, 'wd': 0.0001}
- {'pos_mae_cm': 1.841902494430542, 'vel_base_cm': 4.453004360198975, 'corners_reached': 1.8, 'final_err_cm': 4.593025904436327} | {'hid': 128, 'layers': 3, 'h': 8, 'sigma': 0.04, 'reps': 3, 'epochs': 300, 'lr': 0.0003, 'wd': 0.01}
- {'pos_mae_cm': 1.3121259212493896, 'vel_base_cm': 2.2302894592285156, 'corners_reached': 1.7, 'final_err_cm': 6.1903198514063416} | {'hid': 64, 'layers': 2, 'h': 5, 'sigma': 0.04, 'reps': 3, 'epochs': 300, 'lr': 0.001, 'wd': 0.01}
- {'pos_mae_cm': 1.678009033203125, 'vel_base_cm': 4.453004360198975, 'corners_reached': 1.3, 'final_err_cm': 20.964804039323205} | {'hid': 128, 'layers': 2, 'h': 8, 'sigma': 0.02, 'reps': 3, 'epochs': 100, 'lr': 0.001, 'wd': 0}
- {'pos_mae_cm': 1.6956020593643188, 'vel_base_cm': 4.453004360198975, 'corners_reached': 1.1, 'final_err_cm': 18.02971350792624} | {'hid': 128, 'layers': 2, 'h': 8, 'sigma': 0.02, 'reps': 3, 'epochs': 200, 'lr': 0.0003, 'wd': 0.01}
- mean velocity-extrapolation one-step error over trials: 3.45 cm
## C error->correction switch-time error (s, lower better): 61 trials
- {'switch_err_s_median': 1.1882679462432861, 'switch_err_s_mean': 1.3458888530731201, 'win_acc': 0.817723968822747} | {'W': 60, 'model': 'mlp', 'hid': 64, 'ep': 500}
- {'switch_err_s_median': 1.23695707321167, 'switch_err_s_mean': 2.1591296195983887, 'win_acc': 0.7933991897874213} | {'W': 30, 'model': 'gboost', 'hid': 64, 'ep': 500}
- {'switch_err_s_median': 1.23695707321167, 'switch_err_s_mean': 2.1591296195983887, 'win_acc': 0.7933991897874213} | {'W': 30, 'model': 'gboost', 'hid': 32, 'ep': 500}
- {'switch_err_s_median': 1.2887991666793823, 'switch_err_s_mean': 1.7677761316299438, 'win_acc': 0.7907827404409595} | {'W': 60, 'model': 'mlp', 'hid': 32, 'ep': 1000}
- {'switch_err_s_median': 1.3822386264801025, 'switch_err_s_mean': 2.0259737968444824, 'win_acc': 0.8268563461481889} | {'W': 30, 'model': 'mlp', 'hid': 32, 'ep': 200}
## Series classifier window accuracy (higher better): 61 trials
- {'window_acc': 0.8628246753246753, 'noise_recall': 0.7181008902077152, 'classes': ['A', 'B', 'C', 'D', 'H', 'J'], 'majority': 0.23376623376623376} | {'W': 90, 'model': 'mlp', 'hid': 64, 'ep': 800}
- {'window_acc': 0.8571428571428571, 'noise_recall': 0.6468842729970327, 'classes': ['A', 'B', 'C', 'D', 'H', 'J'], 'majority': 0.23376623376623376} | {'W': 90, 'model': 'mlp', 'hid': 128, 'ep': 800}
- {'window_acc': 0.8563311688311688, 'noise_recall': 0.6824925816023739, 'classes': ['A', 'B', 'C', 'D', 'H', 'J'], 'majority': 0.23376623376623376} | {'W': 90, 'model': 'mlp', 'hid': 128, 'ep': 800}
- {'window_acc': 0.8518668831168831, 'noise_recall': 0.6913946587537092, 'classes': ['A', 'B', 'C', 'D', 'H', 'J'], 'majority': 0.23376623376623376} | {'W': 90, 'model': 'mlp', 'hid': 64, 'ep': 300}
- {'window_acc': 0.8378080176535491, 'noise_recall': 0.6546961325966851, 'classes': ['A', 'B', 'C', 'D', 'H', 'J'], 'majority': 0.2302317028319235} | {'W': 60, 'model': 'mlp', 'hid': 128, 'ep': 300}
