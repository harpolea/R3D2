# -*- coding: utf-8 -*-
"""
Created on Mon Feb 15 11:28:53 2016

@author: ih3
"""

import numpy
from scipy.optimize import brentq
from scipy.integrate import odeint
from copy import deepcopy
from .state import State

def rarefaction_dwdp(w, p, q_known, wavenumber):
    r"""
    There is a tricky point here that needs investigation. If
    the input p is used here, rather than local_state.p, then they
    can diverge (when :math:`v_t` is significant) leading to overflows of g. By
    using local_state we avoid the overflow, but it may mean the final
    state is not very accurate.
    """
    lr_sign = wavenumber - 1
    dwdp = numpy.zeros_like(w)
    rho, v, eps = w
    vt = q_known.vt_from_known(rho, v, eps)
    local_state = State(rho, v, vt, eps, q_known.eos)
    cs = local_state.cs
    h = local_state.h
    W_lorentz = local_state.W_lorentz
    xi = local_state.wavespeed(wavenumber)
    # g quantifies the effect of tangential velocities: see the Living Review
    # and original Pons et al paper for details.
    g = vt**2 * (xi**2 - 1.0) / (1.0 - xi * v)**2
    dwdp[0] = 1.0 / (h * cs**2)
    dwdp[1] = lr_sign / (rho * h * W_lorentz**2 * cs) / numpy.sqrt(1.0 + g)
    dwdp[2] = local_state.p / (rho**2 * h * cs**2)
    return dwdp
    
def mass_flux_squared(q_start, p_end, unknown_eos=None):

    if unknown_eos is None:
        unknown_eos = q_start.eos

    def shock_root_rho(rho):
        h = unknown_eos['h_from_rho_p'](rho, p_end)
        return (h**2 - q_start.h**2) - \
        (h/rho + q_start.h/q_start.rho) * (p_end - q_start.p)

    if p_end >= q_start.p:
        # Shock
        min_rho = q_start.rho
        shock_root_min = shock_root_rho(min_rho)
        max_rho = numpy.sqrt(p_end/q_start.p) * q_start.rho
        shock_root_max = shock_root_rho(max_rho)
        while(shock_root_min * shock_root_max > 0.0):
            min_rho /= 1.1 # Not sure - could end up with unphysical root?
            max_rho *= 10.0
            shock_root_min = shock_root_rho(min_rho)
            shock_root_max = shock_root_rho(max_rho)
    else:
        # Deflagration
        max_rho = q_start.rho
        shock_root_max = shock_root_rho(max_rho)
        min_rho = numpy.sqrt(p_end/q_start.p) * q_start.rho
        shock_root_min = shock_root_rho(min_rho)
        while(shock_root_min * shock_root_max > 0.0):
            min_rho /= 10.0 # Not sure - could end up with unphysical root?
            max_rho *= 1.1
            shock_root_min = shock_root_rho(min_rho)
            shock_root_max = shock_root_rho(max_rho)
    rho = brentq(shock_root_rho, min_rho, max_rho)
    h = unknown_eos['h_from_rho_p'](rho, p_end)
    eps = h - 1.0 - p_end / rho
    dp = p_end - q_start.p
    dh2 = h**2 - q_start.h**2
    j2 = -dp / (dh2 / dp - 2.0 * q_start.h / q_start.rho)

    return j2, rho, eps, dp

def deflagration_root(p_0_star, q_precursor, unknown_eos, wavenumber, label):
    lr_sign = wavenumber - 1    
    j2, rho, eps, dp = mass_flux_squared(q_precursor, p_0_star, unknown_eos)
    j = numpy.sqrt(j2)
    v_deflagration = (q_precursor.rho**2 *
        q_precursor.W_lorentz**2 * q_precursor.v + \
        lr_sign * j**2 * \
        numpy.sqrt(1.0 + q_precursor.rho**2 *
        q_precursor.W_lorentz**2 *
        (1.0 - q_precursor.v**2) / j**2)) / \
        (q_precursor.rho**2 * q_precursor.W_lorentz**2 + j**2)
    W_lorentz_deflagration = 1.0 / numpy.sqrt(1.0 - v_deflagration**2)
    v = (q_precursor.h * q_precursor.W_lorentz *
         q_precursor.v + lr_sign * dp *
         W_lorentz_deflagration / j) / \
        (q_precursor.h * q_precursor.W_lorentz + dp * (1.0 /
         q_precursor.rho / q_precursor.W_lorentz + \
         lr_sign * q_precursor.v *
         W_lorentz_deflagration / j))
    vt = q_precursor.vt_from_known(rho, v, eps)
    q_unknown = State(rho, v, vt, eps, unknown_eos, label)

    return q_unknown.wavespeed(wavenumber) - v_deflagration

def precursor_root(p_0_star, q_known, t_i, wavenumber):
    shock = Shock(q_known, p_0_star, wavenumber)
    q_precursor = shock.q_end
    t_precursor = q_precursor.eos['t_from_rho_eps'](
                    q_precursor.rho, q_precursor.eps)
    return t_precursor - t_i

class WaveSection(object):
    
    def __init__(self, q_start, p_end, wavenumber):
        """
        A part of a wave. For a single shock or rarefaction, this will be the
        complete wave. For a deflagration or detonation, it may form part of
        the full wave.
        """
        self.trivial = False
        assert(wavenumber in [0, 1, 2]), "wavenumber must be 0, 1, 2"
        self.wavenumber = wavenumber
        
    def latex_string(self):
        if self.trivial:
            return ""
        else:
            s = deepcopy(self.name)
            s += r": \lambda^{{({})}}".format(self.wavenumber)
            if len(self.wavespeed) > 1:
                s += r"\in [{:.4f}, {:.4f}]".format(self.wavespeed[0],
                             self.wavespeed[-1])
            else:
                s += r"= {:.4f}".format(self.wavespeed[0])
            return s

    def _repr_latex_(self):
        s = r"$" + self.latex_string() + r"$"
        return s

class Contact(WaveSection):
    
    def __init__(self, q_start, q_end, wavenumber):
        """
        A contact.
        """
        
        self.trivial = False
        assert(wavenumber in [1]), "wavenumber for a Contact must be 1"
        self.type = "Contact"
        self.wavenumber = wavenumber
        self.q_start = deepcopy(q_start)
        self.q_end = deepcopy(q_end)

        self.name = r"{\cal C}"
        
        self.wavespeed = [q_start.v]
        
        assert(numpy.allclose(q_start.v, q_end.v)), "Velocities of states "\
        "must match for a contact"
        assert(numpy.allclose(q_start.p, q_end.p)), "Pressures of states "\
        "must match for a contact"
        assert(numpy.allclose(q_start.wavespeed(wavenumber),
                              q_end.wavespeed(wavenumber))), "Wavespeeds of "\
        "states must match for a contact"
        
    def plotting_data(self):
        
        data = numpy.vstack((self.q_start.state(), self.q_end.state()))
        xi = numpy.array([self.q_start.wavespeed(self.wavenumber),
                       self.q_start.wavespeed(self.wavenumber)])
        
        return xi, data
        
class Rarefaction(WaveSection):
    
    def __init__(self, q_start, p_end, wavenumber):
        """
        A rarefaction.
        """
        
        self.trivial = False
        assert(wavenumber in [0, 2]), "wavenumber for a Rarefaction "\
        "must be in 0, 2"
        assert(q_start.p >= p_end), "For a rarefaction, p_start >= p_end"
        self.type = "Rarefaction"
        self.wavenumber = wavenumber
        self.q_start = deepcopy(q_start)

        self.name = r"{\cal R}"
        if self.wavenumber == 0:
            label = r"\star_L"
            self.name += r"_{\leftarrow}"
        else:
            label = r"\star_R"
            self.name += r"_{\rightarrow}"

        v_known = q_start.wavespeed(self.wavenumber)

        if numpy.allclose(q_start.p, p_end):
            self.trivial = True
            self.q_end = State(q_start.rho, q_start.v, q_start.vt, q_start.eps,
            q_start.eos, label=label)
            v_unknown = v_known
        else:
            w_all = odeint(rarefaction_dwdp,
                           numpy.array([q_start.rho, q_start.v, q_start.eps]),
                           [q_start.p, p_end], rtol = 1e-12, atol = 1e-10,
                           args=((q_start, self.wavenumber)))
            self.q_end = State(w_all[-1, 0], w_all[-1, 1],
                              q_start.vt_from_known(w_all[-1, 0], w_all[-1, 1], w_all[-1, 2]),
                              w_all[-1, 2], q_start.eos, label=label)
            v_unknown = self.q_end.wavespeed(self.wavenumber)

        self.wavespeed = []
        if self.wavenumber == 0:
            self.wavespeed = numpy.array([v_known, v_unknown])
        else:
            self.wavespeed = numpy.array([v_unknown, v_known])
    
    def plotting_data(self):
        # TODO: make the number of points in the rarefaction plot a parameter
        p = numpy.linspace(self.q_start.p, self.q_end.p, 500)
        w_all = odeint(rarefaction_dwdp,
                       numpy.array([self.q_start.rho, self.q_start.v, self.q_start.eps]),
                           p, rtol = 1e-12, atol = 1e-10,
                           args=(self.q_start, self.wavenumber))
        data = numpy.zeros((len(p),8))
        xi = numpy.zeros_like(p)
        for i in range(len(p)):
            state = State(w_all[i,0], w_all[i,1],
                          self.q_start.vt_from_known(w_all[i,0], w_all[i,1], w_all[i,2]),
                          w_all[i, 2], self.q_start.eos)
            xi[i] = state.wavespeed(self.wavenumber)
            data[i,:] = state.state()
        
        return xi, data

class Shock(WaveSection):
    
    def __init__(self, q_start, p_end, wavenumber):
        """
        A shock.
        """

        self.trivial = False
        assert(wavenumber in [0, 2]), "wavenumber for a Shock "\
        "must be in 0, 2"
        # As we use the Shock code for deflagration checks, we can't apply
        # this check
        #assert(q_start.p <= p_end), "For a shock, p_start <= p_end"
        self.type = "Shock"
        self.wavenumber = wavenumber
        lr_sign = self.wavenumber - 1
        self.q_start = deepcopy(q_start)

        self.name = r"{\cal S}"
        if self.wavenumber == 0:
            label = r"\star_L"
            self.name += r"_{\leftarrow}"
        else:
            label = r"\star_R"
            self.name += r"_{\rightarrow}"

        if numpy.allclose(q_start.p, p_end):
            self.trivial = True
            self.q_end = State(q_start.rho, q_start.v, q_start.vt, q_start.eps,
            q_start.eos, label=label)
            v_shock = q_start.wavespeed(self.wavenumber)
        else:
            j2, rho, eps, dp = mass_flux_squared(q_start, p_end, 
                                                      q_start.eos)
            j = numpy.sqrt(j2)
            v_shock = (q_start.rho**2 * q_start.W_lorentz**2 * q_start.v + \
                lr_sign * j**2 * \
                numpy.sqrt(1.0 + q_start.rho**2 * q_start.W_lorentz**2 * (1.0 - q_start.v**2) / j**2)) / \
                (q_start.rho**2 * q_start.W_lorentz**2 + j**2)
            W_lorentz_shock = 1.0 / numpy.sqrt(1.0 - v_shock**2)
            v = (q_start.h * q_start.W_lorentz * q_start.v + lr_sign * dp * W_lorentz_shock / j) / \
                (q_start.h * q_start.W_lorentz + dp * (1.0 / q_start.rho / q_start.W_lorentz + \
                lr_sign * q_start.v * W_lorentz_shock / j))
            vt = q_start.vt_from_known(rho, v, eps)
            self.q_end = State(rho, v, vt, eps, q_start.eos, label=label)

        self.wavespeed = numpy.array([v_shock])
        
    def plotting_data(self):
        
        data = numpy.vstack((self.q_start.state(), self.q_end.state()))
        xi = numpy.array([self.wavespeed[0], self.wavespeed[0]])
        
        return xi, data

# TODO: Check that q is correctly initialized across each wave in det, defl.
class Deflagration(WaveSection):
    
    def __init__(self, q_start, p_end, wavenumber):
        """
        A deflagration.
        """
        
        eos_end = q_start.eos['eos_inert']
        t_i = q_start.eos['t_ignition']

        self.trivial = False
        assert(wavenumber in [0, 2]), "wavenumber for a Deflagration "\
        "must be in 0, 2"
        assert(q_start.p >= p_end), "For a deflagration, p_start >= p_end"
        t_start = q_start.eos['t_from_rho_eps'](q_start.rho, q_start.eps)
        assert(t_start >= t_i), "For a deflagration, temperature of start "\
        "state must be at least the ignition temperature"
        self.type = "Deflagration"
        self.wavenumber = wavenumber
        lr_sign = self.wavenumber - 1
        self.q_start = deepcopy(q_start)
        
        self.name = r"{\cal WDF}"
        if self.wavenumber == 0:
            label = r"\star_L"
            self.name += r"_{\leftarrow}"
        else:
            label = r"\star_R"
            self.name += r"_{\rightarrow}"

        v_known = q_start.wavespeed(self.wavenumber)

        if numpy.allclose(q_start.p, p_end):
            self.trivial = True
            self.q_end = State(q_start.rho, q_start.v, q_start.vt, q_start.eps,
            eos_end, label=label)
            v_deflagration = v_known
        else:
            # This is a single deflagration, so the start state must be at the
            # reaction temperature already.
            j2, rho, eps, dp = mass_flux_squared(q_start, p_end, eos_end)
            j = numpy.sqrt(j2)
            v_deflagration = (q_start.rho**2 *
                q_start.W_lorentz**2 * q_start.v + \
                lr_sign * j**2 * \
                numpy.sqrt(1.0 + q_start.rho**2 *
                q_start.W_lorentz**2 *
                (1.0 - q_start.v**2) / j**2)) / \
                (q_start.rho**2 * q_start.W_lorentz**2 + j**2)
            W_lorentz_deflagration = 1.0 / numpy.sqrt(1.0 - v_deflagration**2)
            v = (q_start.h * q_start.W_lorentz * q_start.v +
                 lr_sign * dp * W_lorentz_deflagration / j) / \
                 (q_start.h * q_start.W_lorentz + dp * (1.0 /
                  q_start.rho / q_start.W_lorentz + \
                 lr_sign * q_start.v * W_lorentz_deflagration / j))
            vt = q_start.vt_from_known(rho, v, eps)
            q_unknown = State(rho, v, vt, eps, eos_end, label=label)

            # If the speed in the unknown state means the characteristics are
            # not going into the deflagration, then this is an unstable strong
            # deflagration
            if (lr_sign*(q_unknown.wavespeed(self.wavenumber) - v_deflagration) < 0):
                p_cjdf = brentq(deflagration_root, (1.0+1e-9)*p_end,
                                (1.0-1e-9)*q_start.p,
                                args=(q_start, eos_end, self.wavenumber, t_i))
                j2, rho, eps, dp = mass_flux_squared(q_start, p_cjdf, eos_end)
                j = numpy.sqrt(j2)
                v_deflagration = (q_start.rho**2 *
                    q_start.W_lorentz**2 * q_start.v + \
                    lr_sign * j**2 * \
                    numpy.sqrt(1.0 + q_start.rho**2 *
                    q_start.W_lorentz**2 *
                    (1.0 - q_start.v**2) / j**2)) / \
                    (q_start.rho**2 * q_start.W_lorentz**2 + j**2)
                W_lorentz_deflagration = 1.0 / numpy.sqrt(1.0 - v_deflagration**2)
                v = (q_start.h * q_start.W_lorentz *
                    q_start.v + lr_sign * dp * W_lorentz_deflagration / j) / \
                    (q_start.h * q_start.W_lorentz + dp * (1.0 /
                     q_start.rho / q_start.W_lorentz + \
                     lr_sign * q_start.v * W_lorentz_deflagration / j))
                vt = q_start.vt_from_known(rho, v, eps)
                q_unknown = State(rho, v, vt, eps, eos_end, label=label)
                self.name = r"{\cal CJDF}"
                if self.wavenumber == 0:
                    label = r"\star_L"
                    self.name += r"_{\leftarrow}"
                else:
                    label = r"\star_R"
                    self.name += r"_{\rightarrow}"

            self.q_end = deepcopy(q_unknown)


        self.wavespeed = numpy.array([v_deflagration, v_deflagration])
    
    def plotting_data(self):
        
        data = numpy.vstack((self.q_start.state(), self.q_end.state()))
        xi = numpy.array([self.q_start.wavespeed(self.wavenumber),
                       self.q_start.wavespeed(self.wavenumber)])
        
        return xi, data

class Detonation(WaveSection):
    
    def __init__(self, q_start, p_end, wavenumber):
        """
        A detonation.
        """
        
        eos_end = q_start.eos['eos_inert']
        t_i = q_start.eos['t_ignition']

        self.trivial = False
        assert(wavenumber in [0, 2]), "wavenumber for a Detonation "\
        "must be in 0, 2"
        assert(q_start.p <= p_end), "For a detonation, p_start <= p_end"
        t_start = q_start.eos['t_from_rho_eps'](q_start.rho, q_start.eps)
        assert(t_start >= t_i), "For a detonation, temperature of start "\
        "state must be at least the ignition temperature"
        self.type = "Detonation"
        self.wavenumber = wavenumber
        lr_sign = self.wavenumber - 1
        self.q_start = deepcopy(q_start)

        self.name = r"{\cal SDT}"
        if self.wavenumber == 0:
            label = r"\star_L"
            self.name += r"_{\leftarrow}"
        else:
            label = r"\star_R"
            self.name += r"_{\rightarrow}"

        v_known = q_start.wavespeed(self.wavenumber)

        if numpy.allclose(q_start.p, p_end):
            self.trivial = True
            self.q_end = State(q_start.rho, q_start.v, q_start.vt, q_start.eps,
            eos_end, label=label)
            v_detonation = v_known
        else:
            # This is a single detonation, so the start state must be at the
            # reaction temperature already.
            j2, rho, eps, dp = mass_flux_squared(q_start, p_end, eos_end)
            j = numpy.sqrt(j2)
            v_detonation = (q_start.rho**2 *
                q_start.W_lorentz**2 * q_start.v + \
                lr_sign * j**2 * \
                numpy.sqrt(1.0 + q_start.rho**2 *
                q_start.W_lorentz**2 *
                (1.0 - q_start.v**2) / j**2)) / \
                (q_start.rho**2 * q_start.W_lorentz**2 + j**2)
            W_lorentz_detonation = 1.0 / numpy.sqrt(1.0 - v_detonation**2)
            v = (q_start.h * q_start.W_lorentz * q_start.v +
                 lr_sign * dp * W_lorentz_detonation / j) / \
                 (q_start.h * q_start.W_lorentz + dp * (1.0 /
                  q_start.rho / q_start.W_lorentz + \
                 lr_sign * q_start.v * W_lorentz_detonation / j))
            vt = q_start.vt_from_known(rho, v, eps)
            q_unknown = State(rho, v, vt, eps, eos_end, label=label)

            # If the speed in the unknown state means the characteristics are
            # not going into the detonation, then this is an unstable weak
            # detonation
            if (lr_sign*(q_unknown.wavespeed(self.wavenumber) - v_detonation) < 0):
                # NOTE: if this truly is the same function, then this whole
                # set of code should be refactored, as it's essentially the
                # same for deflagration and detonation.
                p_cjdt = brentq(deflagration_root, (1.0+1e-9)*p_end,
                                (1.0-1e-9)*q_start.p,
                                args=(q_start, eos_end, self.wavenumber, t_i))
                j2, rho, eps, dp = self.mass_flux_squared(q_start, p_cjdt, eos_end)
                j = numpy.sqrt(j2)
                v_detonation = (q_start.rho**2 *
                    q_start.W_lorentz**2 * q_start.v + \
                    lr_sign * j**2 * \
                    numpy.sqrt(1.0 + q_start.rho**2 *
                    q_start.W_lorentz**2 *
                    (1.0 - q_start.v**2) / j**2)) / \
                    (q_start.rho**2 * q_start.W_lorentz**2 + j**2)
                W_lorentz_detonation = 1.0 / numpy.sqrt(1.0 - v_detonation**2)
                v = (q_start.h * q_start.W_lorentz *
                    q_start.v + lr_sign * dp * W_lorentz_detonation / j) / \
                    (q_start.h * q_start.W_lorentz + dp * (1.0 /
                     q_start.rho / q_start.W_lorentz + \
                     lr_sign * q_start.v * W_lorentz_detonation / j))
                vt = q_start.vt_from_known(rho, v, eps)
                q_unknown = State(rho, v, vt, eps, eos_end, label=label)
                self.name = r"{\cal CJDT}"
                if self.wavenumber == 0:
                    label = r"\star_L"
                    self.name += r"_{\leftarrow}"
                else:
                    label = r"\star_R"
                    self.name += r"_{\rightarrow}"

            self.q_end = deepcopy(q_unknown)


        self.wavespeed = numpy.array([v_detonation, v_detonation])
    
    def plotting_data(self):
        
        data = numpy.vstack((self.q_start.state(), self.q_end.state()))
        xi = numpy.array([self.q_start.wavespeed(self.wavenumber),
                       self.q_start.wavespeed(self.wavenumber)])
        
        return xi, data

def build_inert_wave_section(q_known, unknown_value, wavenumber):
    """
    Object factory for the WaveSection; non-reactive case
    """
    
    if wavenumber == 1:
        return [Contact(q_known, unknown_value, wavenumber)]
    elif q_known.p < unknown_value:
        return [Shock(q_known, unknown_value, wavenumber)]
    else:
        return [Rarefaction(q_known, unknown_value, wavenumber)]
        
def build_reactive_wave_section(q_known, unknown_value, wavenumber):
    """
    Object factory for the WaveSection; reactive case
    """
    
    t_i = q_known.eos['t_ignition']    
    
    if wavenumber == 1:
        return Contact(q_known, unknown_value, wavenumber)
    else:
        wavesections = []
        if q_known.p < unknown_value:
            # The detonation wave
            detonation = Detonation(q_known, unknown_value, wavenumber)
            wavesections.append(detonation)
            q_next = deepcopy(detonation.q_end)
            # Finally, was it a CJ detonation?
            if q_next.p > unknown_value:
                rarefaction = Rarefaction(q_next, unknown_value, wavenumber)
                wavesections.append(rarefaction)
        else:
            t_known = q_known.eos['t_from_rho_eps'](q_known.rho, q_known.eps)
            if t_known < t_i: # Need a precursor shock
                p_min = unknown_value
                p_max = q_known.p
                t_min = precursor_root(p_min, q_known, t_i, wavenumber)
                t_max = precursor_root(p_max, q_known, t_i, wavenumber)
                assert(t_min < 0)
    
                if t_max <= 0:
                    p_max *= 2
                    t_max = precursor_root(p_max, q_known, t_i, wavenumber)
    
                p_0_star = brentq(precursor_root, p_min, p_max,
                                  args=(q_known, t_i, wavenumber))
                precursor_shock = Shock(q_known, p_0_star, wavenumber)
                wavesections.append(precursor_shock)
                q_next = precursor_shock.q_end
                q_next.q = q_known.q # No reaction across inert precursor
            else: # No precursor shock
                q_next = deepcopy(q_known)
            # Next, the deflagration wave
            deflagration = Deflagration(q_next, unknown_value, wavenumber)
            wavesections.append(deflagration)
            q_next = deepcopy(deflagration.q_end)
            # Finally, was it a CJ deflagration?
            if q_next.p > unknown_value:
                rarefaction = Rarefaction(q_next, unknown_value, wavenumber)
                wavesections.append(rarefaction)

        return wavesections
        

class Wave(object):  
    
    def __init__(self, q_known, unknown_value, wavenumber):
        """
        A wave.
        
        Parameters
        ----------

        self : Wave
            The wave, which has a known state on one side and an unknown
            state on the other side.
        q_known : State
            The known state on one side of the wave
        p_star : scalar
            Pressure in the region of unknown state
        unknown_eos : dictionary
            Equation of state in the unknown region
        t_i : scalar
            temperature at which the state starts to react
        """
        
        self.wavenumber = wavenumber
        self.wave_sections = []
        self.wavespeed = []
        
        if 'q_available' not in q_known.eos:
            waves = build_inert_wave_section(q_known, unknown_value, 
                                             wavenumber)
            for sections in waves:
                self.wave_sections.append(sections)
        else:
            waves = build_reactive_wave_section(q_known, unknown_value,
                                                wavenumber)
            for sections in waves:
                self.wave_sections.append(sections)

        self.name = self.wave_sections_latex_string()
        if wavenumber == 0:
            self.q_l = deepcopy(q_known)
            if self.wave_sections:
                self.q_r = self.wave_sections[-1].q_end
            else:
                self.q_r = deepcopy(self.q_l)
        elif wavenumber == 1:
            self.q_l = deepcopy(q_known)
            self.q_r = deepcopy(q_known)
        else:
            self.q_r = deepcopy(q_known)
            if self.wave_sections:
                self.q_l = self.wave_sections[-1].q_end
            else:
                self.q_l = deepcopy(self.q_r)
    
        minspeed = 10
        maxspeed = -10
        if self.wave_sections:
            for wavesection in self.wave_sections:
                for speed in wavesection.wavespeed:
                    minspeed = min(speed, minspeed)
                    maxspeed = max(speed, maxspeed)
        self.wavespeed.append(minspeed)
        if not numpy.allclose(minspeed, maxspeed):
            self.wavespeed.append(maxspeed)
            
    def plotting_data(self):
        
        xi_wave = numpy.zeros((0,))
        data_wave = numpy.zeros((0,8))
        for wavesection in self.wave_sections:
            xi_section, data_section = wavesection.plotting_data()
            xi_wave = numpy.hstack((xi_wave, xi_section))
            data_wave = numpy.vstack((data_wave, data_section))
        
        if self.wavenumber == 2:
            data_wave = data_wave[-1::-1,:]
        
        return xi_wave, data_wave
    
    def wave_sections_latex_string(self):
        if len(self.wave_sections)==0:
            return ""
        elif len(self.wave_sections)==1:
            s = self.wave_sections[0].name
        else:
            s = r"\left("
            if self.wavenumber == 2:
                for wavesection in reversed(self.wave_sections):
                    s += wavesection.name
            else:
                for wavesection in self.wave_sections:
                    s += wavesection.name
            s += r"\right) "
        return s
        
    def latex_string(self):
        s = self.wave_sections_latex_string()
        if len(self.wave_sections)==0:
            return ""
        elif len(self.wave_sections)==1:
            speeds = self.wave_sections[0].wavespeed
        else:
            speeds = [self.wave_sections[0].wavespeed[0],
                      self.wave_sections[-1].wavespeed[-1]]
        s += r": \lambda^{{({})}}".format(self.wavenumber)
        s += r"\in [{:.4f}, {:.4f}]".format(min(speeds), max(speeds))
        return s
        
    def _repr_latex_(self):
        s = r"$" + self.latex_string() + r"$"
        return s