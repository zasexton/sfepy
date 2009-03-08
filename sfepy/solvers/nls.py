from sfepy.base.base import *
from sfepy.solvers.solvers import NonlinearSolver
import sfepy.base.plotutils as plu

##
# 13.12.2005, c
# 14.12.2005
# 02.10.2007
def check_tangent_matrix( conf, vec_x0, mtx_a0, fun, fun_grad ):
    vec_x = vec_x0.copy()
    delta = conf.delta

    vec_r = fun( vec_x ) # Update state.
    mtx_a0 = fun_grad( vec_x, mtx_a0 )

    mtx_a = mtx_a0.tocsc()
    mtx_d = mtx_a.copy()
    mtx_d.data[:] = 0.0

    vec_dx = nm.zeros_like( vec_r )

    for ic in range( vec_dx.shape[0] ):
        vec_dx[ic] = delta
        xx = vec_x.copy() - vec_dx
        vec_r1 = fun( xx )

        vec_dx[ic] = -delta
        xx = vec_x.copy() - vec_dx
        vec_r2 = fun( xx )

        vec_dx[ic] = 0.0;

        vec = 0.5 * (vec_r2 - vec_r1) / delta

##         ir = mtx_a.indices[mtx_a.indptr[ic]:mtx_a.indptr[ic+1]]
##         for ii in ir:
##             mtx_d[ii,ic] = vec[ii]

        ir = mtx_a.indices[mtx_a.indptr[ic]:mtx_a.indptr[ic+1]]
        mtx_d.data[mtx_a.indptr[ic]:mtx_a.indptr[ic+1]] = vec[ir]


    vec_r = fun( vec_x ) # Restore.

    tt = time.clock()
    print mtx_a, '.. analytical'
    print mtx_d, '.. difference'
    plu.plot_matrix_diff( mtx_d, mtx_a, delta, ['difference', 'analytical'],
                        conf.check )

    return time.clock() - tt

##
# c: 02.12.2005, r: 02.04.2008
def conv_test( conf, it, err, err0 ):

    status = -1
    if (abs( err0 ) < conf.macheps):
        err_r = 0.0
    else:
        err_r = err / err0

    output( 'nls: iter: %d, residual: %e (rel: %e)' % (it, err, err_r) )
    if it > 0:
        if (err < conf.eps_a) and (err_r < conf.eps_r):
            status = 0
    else:
        if err < conf.eps_a:
            status = 0

    if (status == -1) and (it >= conf.i_max):
        status = 1

    return status

##
# 10.10.2007, c
class Newton( NonlinearSolver ):
    name = 'nls.newton'

    def process_conf( conf ):
        """
        Missing items are set to default values for a linear problem.
        
        Example configuration, all items:
        
        solver_1 = {
            'name' : 'newton',
            'kind' : 'nls.newton',

            'i_max'      : 2,
            'eps_a'      : 1e-8,
            'eps_r'      : 1e-2,
            'macheps'   : 1e-16,
            'lin_red'    : 1e-2, # Linear system error < (eps_a * lin_red).
            'ls_red'     : 0.1,
            'ls_red_warp' : 0.001,
            'ls_on'      : 0.99999,
            'ls_min'     : 1e-5,
            'check'     : 0,
            'delta'     : 1e-6,
            'is_plot'    : False,
            'problem'   : 'nonlinear', # 'nonlinear' or 'linear' (ignore i_max)
        }
        """
        get = conf.get_default_attr

        i_max = get( 'i_max', 1 )
        eps_a = get( 'eps_a', 1e-10 )
        eps_r = get( 'eps_r', 1.0 )
        macheps = get( 'macheps', nm.finfo( nm.float64 ).eps )
        lin_red = get( 'lin_red', 1.0 )
        ls_red = get( 'ls_red', 0.1 )
        ls_red_warp = get( 'ls_red_warp', 0.001 )
        ls_on = get( 'ls_on', 0.99999 )
        ls_min = get( 'ls_min', 1e-5 )
        check = get( 'check', 0 )
        delta = get( 'delta', 1e-6)
        is_plot = get( 'is_plot', False )
        problem = get( 'problem', 'nonlinear' )

        common = NonlinearSolver.process_conf( conf )
        return Struct( **locals() ) + common
    process_conf = staticmethod( process_conf )

    ##
    # 10.10.2007, c
    def __init__( self, conf, **kwargs ):
        NonlinearSolver.__init__( self, conf, **kwargs )

    ##
    # c: 02.12.2005, r: 04.04.2008
    # 10.10.2007, from newton()
    def __call__( self, vec_x0, conf = None, fun = None, fun_grad = None,
                  lin_solver = None, status = None ):
        """setting conf.problem == 'linear' means 1 iteration and no rezidual
        check!
        """
        conf = get_default( conf, self.conf )
        fun = get_default( fun, self.fun )
        fun_grad = get_default( fun_grad, self.fun_grad )
        lin_solver = get_default( lin_solver, self.lin_solver )
        status = get_default( status, self.status )

        time_stats = {}

        vec_x = vec_x0.copy()
        vec_x_last = vec_x0.copy()
        vec_dx = None

        err0 = -1.0
        err_last = -1.0
        it = 0
        while 1:

            ls = 1.0
            vec_dx0 = vec_dx;
            while 1:
                tt = time.clock()
                try:
                    vec_r = fun( vec_x )
                except ValueError:
                    ok = False
                else:
                    ok = True
                    
                time_stats['rezidual'] = time.clock() - tt
                if ok:
                    try:
                        err = nla.norm( vec_r )
                    except:
                        output( 'infs or nans in the residual:', vec_r )
                        output( nm.isfinite( vec_r ).all() )
                        debug()
                    if it == 0:
                        err0 = err;
                        break
                    if err < (err_last * conf.ls_on): break
                    red = conf.ls_red;
                    output( 'linesearch: iter %d, (%.5e < %.5e) (new ls: %e)'\
                            % (it, err, err_last * conf.ls_on, red * ls) )
                else: # Failure.
                    red = conf.ls_red_warp;
                    output(  'rezidual computation failed for iter %d'
                             ' (new ls: %e)!' % (it, red * ls) )
                    if (it == 0):
                        raise RuntimeError, 'giving up...'

                if ls < conf.ls_min:
                    if not ok:
                        raise RuntimeError, 'giving up...'
                    output( 'linesearch failed, continuing anyway' )
                    break

                ls *= red;

                vec_dx = ls * vec_dx0;
                vec_x = vec_x_last.copy() - vec_dx
            # End residual loop.

            err_last = err;
            vec_x_last = vec_x.copy()

            condition = conv_test( conf, it, err, err0 )
            if condition >= 0:
                break

            tt = time.clock()
            if conf.problem == 'nonlinear':
                try:
                    mtx_a = fun_grad( vec_x )
                except ValueError:
                    ok = False
                else:
                    ok = True
            else:
                mtx_a, ok = fun_grad( 'linear' ), True
            time_stats['matrix'] = time.clock() - tt
            if not ok:
                raise RuntimeError, 'giving up...'

            if conf.check:
                tt = time.clock()
                wt = check_tangent_matrix( conf, vec_x, mtx_a, fun, fun_grad )
                time_stats['check'] = time.clock() - tt - wt
    ##            if conf.check == 2: pause()

            tt = time.clock() 
            vec_dx = lin_solver( vec_r, mtx = mtx_a )
            time_stats['solve'] = time.clock() - tt

            for kv in time_stats.iteritems():
                output( '%10s: %7.2f [s]' % kv )

            vec_e = mtx_a * vec_dx - vec_r
            lerr = nla.norm( vec_e )
            if lerr > (conf.eps_a * conf.lin_red):
                output( 'linear system not solved! (err = %e)' % lerr )
    #            raise RuntimeError, 'linear system not solved! (err = %e)' % lerr

            vec_x -= vec_dx

            if conf.is_plot:
                plu.pylab.ion()
                plu.pylab.gcf().clear()
                plu.pylab.subplot( 2, 2, 1 )
                plu.pylab.plot( vec_x_last )
                plu.pylab.ylabel( r'$x_{i-1}$' )
                plu.pylab.subplot( 2, 2, 2 )
                plu.pylab.plot( vec_r )
                plu.pylab.ylabel( r'$r$' )
                plu.pylab.subplot( 2, 2, 4 )
                plu.pylab.plot( vec_dx )
                plu.pylab.ylabel( r'$\_delta x$' )
                plu.pylab.subplot( 2, 2, 3 )
                plu.pylab.plot( vec_x )
                plu.pylab.ylabel( r'$x_i$' )
                plu.pylab.draw()
                plu.pylab.ioff()
                pause()

            it += 1

        if status is not None:
            status['time_stats'] = time_stats
            status['err0'] = err0
            status['err'] = err
            status['condition'] = condition

        return vec_x

class ScipyBroyden( NonlinearSolver ):
    """Interface to Broyden and Anderson solvers from scipy.optimize."""

    name = 'nls.scipy_broyden_like'

    def process_conf( conf ):
        """
        Missing items are left to scipy defaults. Unused options are ignored.
        
        Example configuration, all items:
        
        solver_1 = {
            'name' : 'broyden',
            'kind' : 'nls.scipy_broyden_like',

            'method'  : 'broyden3',
            'i_max'   : 10,
            'alpha'   : 0.9,
            'M'       : 5,
            'w0'      : 0.1,
            'verbose' : True,
        }
        """
        get = conf.get_default_attr

        method = get( 'method', 'broyden3' )
        i_max = get( 'i_max' )
        alpha = get( 'alpha' )
        M = get( 'M' )
        w0 = get( 'w0' )
        verbose = get( 'verbose' )

        common = NonlinearSolver.process_conf( conf )
        return Struct( **locals() ) + common
    process_conf = staticmethod( process_conf )

    def __init__( self, conf, **kwargs ):
        NonlinearSolver.__init__( self, conf, **kwargs )
        self.set_method( self.conf )

    def set_method( self, conf ):
        import scipy.optimize as so

        try:
            solver = getattr( so, conf.method )
        except AttributeError:
            output( 'scipy solver %s does not exist!' % conf.method )
            output( 'using broyden3 instead' )
            solver = so.broyden3
        self.solver = solver

    def __call__( self, vec_x0, conf = None, fun = None, fun_grad = None,
                  lin_solver = None, status = None ):
        if conf is not None:
            self.set_method( conf )
        else:
            conf = self.conf
        fun = get_default( fun, self.fun )
        status = get_default( status, self.status )

        tt = time.clock()

        kwargs = {'iter' : conf.i_max,
                  'alpha' : conf.alpha,
                  'verbose' : conf.verbose}

        if conf.method == 'broyden_generalized':
            kwargs.update( {'M' : conf.M} )

        elif conf.method in ['anderson', 'anderson2']:
            kwargs.update( {'M' : conf.M, 'w0' : conf.w0} )

        vec_x = self.solver( fun, vec_x0, **kwargs )
        
        if status is not None:
            status['time_stats'] = time.clock() - tt

        return vec_x
