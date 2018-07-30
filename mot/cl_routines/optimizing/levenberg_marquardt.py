import os
from pkg_resources import resource_filename
from mot.kernel_data import Zeros
from .base import AbstractParallelOptimizer

__author__ = 'Robbert Harms'
__date__ = "2014-02-05"
__license__ = "LGPL v3"
__maintainer__ = "Robbert Harms"
__email__ = "robbert.harms@maastrichtuniversity.nl"


class LevenbergMarquardt(AbstractParallelOptimizer):

    default_patience = 250

    def __init__(self, patience=None, step_bound=None, scale_diag=None, optimizer_settings=None, **kwargs):
        """Use the Levenberg-Marquardt method to calculate the optimimum.

        Args:
            patience (int): Used to set the maximum number of iterations to patience*(number_of_parameters+1)
        """
        patience = patience or self.default_patience

        optimizer_settings = optimizer_settings or {}

        keyword_values = {}
        keyword_values['step_bound'] = step_bound
        keyword_values['scale_diag'] = scale_diag

        option_defaults = {'step_bound': 100.0, 'scale_diag': 1}

        def get_value(option_name):
            value = keyword_values.get(option_name)
            if value is None:
                value = optimizer_settings.get(option_name)
            if value is None:
                value = option_defaults[option_name]
            return value

        for option in option_defaults:
            optimizer_settings.update({option: get_value(option)})

        super(LevenbergMarquardt, self).__init__(patience=patience, optimizer_settings=optimizer_settings, **kwargs)

    def minimize(self, model, starting_positions):
        if model.get_nmr_observations() < starting_positions.shape[1]:
            raise ValueError('The number of instances per problem must be greater than the number of parameters')
        return super(LevenbergMarquardt, self).minimize(model, starting_positions)

    def _get_optimizer_kernel_data(self, model, nmr_params, nmr_problems):
        return {'_fjac_all': Zeros((nmr_problems,
                                    nmr_params,
                                    model.get_nmr_observations()), ctype='mot_float_type',
                                   is_writable=True, is_readable=True)}

    def _get_optimizer_call_args(self):
        return super(LevenbergMarquardt, self)._get_optimizer_call_args() + ['data->_fjac_all']

    def _get_evaluate_function(self, model, nmr_params):
        """Get the CL code for the evaluation function. This is called from _get_optimizer_cl_code.

        Implementing optimizers can change this if desired.

        Returns:
            str: the evaluation function.
        """
        objective_func = model.get_objective_function()
        kernel_source = ''
        kernel_source += objective_func.get_cl_code()
        kernel_source += '''
            void evaluate(mot_float_type* x, void* data_void, mot_float_type* result){
                mot_data_struct* data = (mot_data_struct*)data_void;
                
                ''' + objective_func.get_cl_function_name() + '''(data, x, 0, result, 0);
                
                // The LM method automatically squares the results, but the model also already does this.
                for(uint i = 0; i < ''' + str(model.get_nmr_observations()) + '''; i++){
                    result[i] = sqrt(fabs(result[i]));
                }
            }
        '''
        return kernel_source

    def _get_optimization_function(self, model, nmr_params):
        params = {'NMR_PARAMS': nmr_params,
                  'PATIENCE': self.patience,
                  'NMR_OBSERVATIONS': model.get_nmr_observations(),
                  'USER_TOL_MULT': 30}

        optimizer_settings = self._optimizer_settings or {}
        option_defaults = {'step_bound': 100.0, 'scale_diag': 1, 'usertol_mult': 30}
        option_converters = {'scale_diag': lambda val: int(bool(val))}

        for option, default in option_defaults.items():
            v = optimizer_settings.get(option, default)
            if option in option_converters:
                v = option_converters[option](v)
            params.update({option.upper(): v})

        with open(os.path.abspath(resource_filename('mot', 'data/opencl/lmmin.cl')), 'r') as f:
            body = f.read()

        if params:
            body = body % params
        return body

    def _get_optimizer_call_name(self):
        return 'lmmin'
