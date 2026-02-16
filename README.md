# Microgridspy TES integration
Compared to the standard MicroGridSpy model, the developed extension explicitly introduces the thermal demand of a cold storage room as an additional system load, alongside the traditional electrical load.

The thermal demand represents the cooling requirement needed to maintain the internal temperature of the cold room and its stored products at the desired set-point. Cooling can be provided through two alternative configurations:

- Direct cooling via compressor, where heat is extracted from the cold room through a conventional refrigeration cycle.

- Cooling through ice-based Thermal Energy Storage (TES).

In the TES configuration, photovoltaic panels generate electrical energy that powers a compressor. The compressor cools a refrigerant fluid and enables the formation of ice inside an insulated storage tank (ice battery). Energy is thus stored in the form of latent heat of fusion.

When cooling is required, the air inside the cold room is circulated through a heat exchanger immersed in the ice. During melting, the ice absorbs heat from the air, thereby cooling the environment and the stored products.

In this way, the system integrates electrical storage (batteries) and thermal storage (TES), allowing the decoupling of photovoltaic energy production from the cooling demand.

<img width="802" height="478" alt="image" src="https://github.com/user-attachments/assets/2af25e89-a439-4b28-9115-757e106b87de" />


# MicroGridSpy Code Modifications

New parameters and decision variables were introduced to describe the physical and economic behavior of the cooling system. These elements were subsequently integrated into the initialization workflow (initialize.py) and into the core model definition (model.py).

Two new constraint modules were added:

### compressor_constraints: 
Direct Cooling Compressor Model

#### **Main physical relationship**

$$
Q_{\text{cooling}} = COP_{\text{direct}} \cdot P_{\text{electric}}
$$

where: 

- $Q_{\text{cooling}}$ = cooling power delivered to the cold room [W]  
- $COP_{\text{direct}}$ = coefficient of performance of the direct compressor [-]  
- $P_{\text{electric}}$ = electric power absorbed by the compressor [W]  

#### **Capacity bound**

$$
Q_{\text{cooling}} \leq \text{Compressor}_{\text{capacity}}
$$

This ensures that the delivered cooling power cannot exceed the installed compressor capacity.

### TES_constraints:
Ice-based Thermal Energy Storage (TES) Model:

The TES system is modeled through state-of-charge dynamics, flow constraints, and ice production equations linked to compressor operation.

#### 1. State of Charge (SOC) Dynamics

$$
SOC(t) = SOC(t-1) \cdot \eta_{\text{storage}} + \left( \dot{m}_{\text{charge}}(t) - \dot{m}_{\text{discharge}}(t) \right) \cdot \Delta t
$$

where:

- $SOC(t)$ = state of charge of the TES [kg]  
- $\eta_{\text{storage}}$ = storage efficiency [-]  
- $\dot{m}_{\text{charge}}$ = charging mass flow rate [kg/h]  
- $\dot{m}_{\text{discharge}}$ = discharging mass flow rate [kg/h]  
- $\Delta t$ = time step duration [h]  

**SOC bounds**

$$
0 \leq SOC(t) \leq TES_{\text{capacity}}
$$

#### 2. Charge and Discharge Flow Constraints

$$
\dot{m}_{\text{charge}}(t) \leq TES_{\text{max charge rate}}
$$

$$
\dot{m}_{\text{discharge}}(t) \leq TES_{\text{max discharge rate}}
$$

$$
\dot{m}_{\text{charge}}(t) \geq 0
$$

$$
\dot{m}_{\text{discharge}}(t) \geq 0
$$

#### 3. Ice Production

The production of ice is linked to the electrical consumption of the TES compressor:

$$
\dot{m}_{\text{ice}}(t) \cdot Q_{\text{per kg}} = COP_{\text{TES}} \cdot P_{\text{electric}}(t)
$$

where:

- $\dot{m}_{\text{ice}}$ = ice production rate [kg/h]  
- $Q_{\text{per kg}}$ = specific cooling energy per kg of ice [Wh/kg]  
- $COP_{\text{TES}}$ = coefficient of performance of the TES compressor [-]  
- $P_{\text{electric}}$ = electric power absorbed by the TES compressor [W]  

#### 4. TES Compressor Capacity Constraints

Electrical power limit:

$$
P_{\text{electric}}(t) \leq TES_{\text{compressor capacity}}
$$

Ice production limit derived from installed compressor capacity:

$$
\dot{m}_{\text{ice}}(t) \leq 
\frac{TES_{\text{compressor capacity}} \cdot COP_{\text{TES}}}
{Q_{\text{per kg}}}
$$


#### 5. Production–Charge Coupling

All produced ice is assumed to be used for TES charging:

$$
\dot{m}_{\text{charge}}(t) = \dot{m}_{\text{ice}}(t)
$$

### Thermal and Electrical Energy Balance

##### 1. Thermal Balance

$$
Q_{\text{direct}}(t) + Q_{\text{TES}}(t) \geq Q_{\text{th demand}}(t)
$$

(If the direct compressor is disabled, $Q_{\text{direct}}(t)$ is not considered.
If the TES is disabled, $Q_{\text{TES}}(t)$ is not considered.)

where:

- $Q_{\text{direct}}(t)$ = cooling output from the direct compressor [W]

- $Q_{\text{TES}}(t)$ = cooling output from TES discharge [W]

- $Q_{\text{th demand}}(t)$ = thermal demand of the cold room [W]

The TES cooling contribution is derived from discharge mass flow:

$$
Q_{\text{TES}}(t) = \dot{m}_{\text{discharge}}(t) \cdot Q_{\text{per kg}}
$$

##### - Direct Cooling Definition

$$
Q_{\text{direct}}(t) = Q_{\text{cooling, compressor}}(t)
$$

where:

- $Q_{\text{cooling, compressor}}(t)$ = cooling output of the direct compressor [Wh]

##### 2. Electrical Balance

$$
E_{\text{PV}}(t) + E_{\text{battery}}(t) + E_{\text{generator}}(t) + E_{\text{grid}}(t) - E_{\text{losses}}(t) = E_{\text{village}}(t) + E_{\text{extra}}(t)
$$

where:

- $E_{\text{PV}}(t)$ = photovoltaic production [Wh]  
- $E_{\text{battery}}(t)$ = battery discharge [Wh]  
- $E_{\text{generator}}(t)$ = generator production [Wh]  
- $E_{\text{grid}}(t)$ = grid import [Wh]  
- $E_{\text{losses}}(t)$ = electrical losses [Wh]  
- $E_{\text{village}}(t)$ = base electric demand [Wh]  
- $E_{\text{extra}}(t)$ = additional electric demand due to cooling system [Wh]

#### - Extra Electrical Demand

$$
E_{\text{extra}}(t) = E_{\text{compressor}}(t) + E_{\text{TES}}(t)
$$

where:

- $E_{\text{compressor}}(t)$ = electric consumption of the direct compressor [Wh]  
- $E_{\text{TES}}(t)$ = electric consumption of the TES compressor [Wh]

### Project cost

#### Direct Compressor

#### - Investment Cost

$$
C_{\text{inv, direct}} = \text{Compressor}_{\text{capacity}} \cdot c_{\text{spec, direct}}
$$

where:

- $C_{\text{inv, direct}}$ = investment cost of direct compressor [USD]  
- $\text{Compressor}_{\text{capacity}}$ = installed direct compressor capacity [W]  
- $c_{\text{spec, direct}}$ = specific investment cost of direct compressor [USD/W]

#### - OM Cost

$$
C_{\text{OM, direct}} = C_{\text{inv, direct}} \cdot f_{\text{OM, direct}}
$$

where:

- $f_{\text{OM, direct}}$ = OM cost fraction [-]

#### TES Compressor

#### - Investment Cost

$$
C_{\text{inv, TES comp}} = TES_{\text{compressor capacity}} \cdot c_{\text{spec, TES comp}}
$$

where:

- $C_{\text{inv, TES comp}}$ = investment cost of TES compressor [USD]  
- $TES_{\text{compressor capacity}}$ = installed TES compressor capacity [W]  
- $c_{\text{spec, TES comp}}$ = specific investment cost of TES compressor [USD/W]

#### - OM Cost

$$
C_{\text{OM, TES comp}} = C_{\text{inv, TES comp}} \cdot f_{\text{OM, TES comp}}
$$

where:

- $f_{\text{OM, TES comp}}$ = OM cost fraction [-]

### Simultaneity Penalty

Simultaneous charging and discharging of the TES is economically penalized.

For each time step, the overlap variable `tes_overlap` is multiplied by a penalty factor `TES_SIMULTANEITY_PENALTY`.

$$
C_{\text{sim}} = \sum_t \left( TES_{\text{overlap}} \cdot TES_{\text{simultaneity-penality}} \right)
$$

This cost is added to the total scenario cost to discourage simultaneous TES operation.


