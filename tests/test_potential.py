import tempfile
import numpy as np
import tensorflow as tf
from helpers import assert_almost_equal
from shutil import rmtree
from ase import Atoms

def test_pinn_potential():
    testpath = tempfile.mkdtemp()    
    network_params = {
        'ii_nodes':[8, 8],
        'pi_nodes':[8, 8],
        'pp_nodes':[8, 8],
        'en_nodes':[8, 8],
        'depth': 3,
        'rc': 5.,
        'n_basis': 5,
        'atom_types': [1]
    }
    params = {
        'model_dir': testpath,
        'network': 'pinn_network',
        'network_params': network_params,
        'model_params': {'use_force': True,
                         'e_dress':{1:0.5}, 'e_scale':5.0, 'e_unit':2.0}
    }
    _potential_tests(params)
    rmtree(testpath)

def test_bpnn_potential():
    testpath = tempfile.mkdtemp()
    network_params = {
        'sf_spec':[
            {'type':'G2', 'i': 1, 'j': 1, 'eta': [0.1, 0.1, 0.1], 'Rs': [1., 2., 3.]},
            {'type':'G3', 'i': 1, 'j': 1, 'k':1,
             'eta': [0.1, 0.1, 0.1, 0.1], 'lambd': [1., 1., -1., -1.], 'zeta':[1., 1., 4., 4.]},
            {'type':'G4', 'i': 1, 'j': 1, 'k':1,
             'eta': [0.1, 0.1, 0.1, 0.1], 'lambd': [1., 1., -1., -1.], 'zeta':[1., 1., 4., 4.]}            
        ],
        'nn_spec':{1: [8, 8]},
        'rc': 5.,
    }
    
    params = {
        'model_dir': testpath,
        'network': 'bpnn_network',
        'network_params': network_params,
        'model_params': {'use_force': True,
                         'e_dress':{1:0.5}, 'e_scale':5.0, 'e_unit':2.0}
    }
    
    _potential_tests(params)
    rmtree(testpath)


def _get_lj_data():
    from ase.calculators.lj import LennardJones
    
    atoms = Atoms('H3', positions=[[0,0,0],[0,1,0],[1,1,0]])
    atoms.set_calculator(LennardJones(rc=5.0))
    coord, elems, e_data, f_data = [], [], [], []
    for x_a in np.linspace(-5, 0, 1000):
        atoms.positions[0, 0] = x_a
        coord.append(atoms.positions.copy())
        elems.append(atoms.numbers)
        e_data.append(atoms.get_potential_energy())
        f_data.append(atoms.get_forces())
    
    data = {
        'coord': np.array(coord),
        'elems': np.array(elems),
        'e_data': np.array(e_data),
        'f_data': np.array(f_data)
    }
    return data
    

def _potential_tests(params):
    # Series of tasks that a potential should pass
    from pinn.io import load_numpy, sparse_batch
    from pinn.models import potential_model
    from pinn.calculator import PiNN_calc    

    data = _get_lj_data()
    train = lambda: load_numpy(data, split=1).repeat().shuffle(500).apply(sparse_batch(50))
    test = lambda: load_numpy(data, split=1).apply(sparse_batch(10))
    train_spec = tf.estimator.TrainSpec(input_fn=train, max_steps=1e3)
    eval_spec = tf.estimator.EvalSpec(input_fn=test, steps=100)
    

    model = potential_model(params)
    results,_ = tf.estimator.train_and_evaluate(model, train_spec, eval_spec)
    
    # The calculator should be accessable with model_dir
    atoms = Atoms('H3', positions=[[0,0,0],[0,1,0],[1,1,0]])
    calc = PiNN_calc(potential_model(params['model_dir']),
                     properties=['energy', 'forces', 'stress'])
    
    # Test energy dress and scaling
    # Make sure we have the correct error reports
    e_pred, f_pred = [], []
    for coord in data['coord']:
        atoms.positions = coord
        calc.calculate(atoms)
        e_pred.append(calc.get_potential_energy())
        f_pred.append(calc.get_forces())

    f_pred = np.array(f_pred)
    e_pred = np.array(e_pred)

    assert_almost_equal(results['METRICS/F_RMSE']/params['model_params']['e_scale'],
                        np.sqrt(np.mean((f_pred/params['model_params']['e_unit'] 
                                         - data['f_data'])**2)))
    assert_almost_equal(results['METRICS/E_RMSE']/params['model_params']['e_scale'], 
                        np.sqrt(np.mean((e_pred/params['model_params']['e_unit'] 
                                         - data['e_data'])**2)))
    
    # Test energy conservation
    e_pred, f_pred = [], []
    x_a_range = np.linspace(-6, -3, 500)
    for x_a in np.linspace(-6, -3, 500):
        atoms.positions[0, 0] = x_a
        calc.calculate(atoms)
        e_pred.append(calc.get_potential_energy())
        f_pred.append(calc.get_forces())
    e_pred = np.array(e_pred)
    f_pred = np.array(f_pred)
    
    de = e_pred[-1] - e_pred[0]
    int_f = np.trapz(f_pred[:,0,0], x=x_a_range)
    assert_almost_equal(de, -int_f)
    
    # Test virial pressure
    e_pred, p_pred = [], []
    l_range = np.linspace(3,3.5,500)
    atoms.positions[0, 0] = 0
    atoms.set_cell([3,3,3])
    atoms.set_pbc(True)
    for l in l_range:
        atoms.set_cell([l,l,l], scale_atoms=True)
        calc.calculate(atoms)
        e_pred.append(calc.get_potential_energy())
        p_pred.append(np.sum(np.trace(calc.get_stress()))/3/l**3)
        
    de = e_pred[-1] - e_pred[0]
    int_p = np.trapz(p_pred,x=l_range**3)
    assert_almost_equal(de, int_p)