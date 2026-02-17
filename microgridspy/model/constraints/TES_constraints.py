import xarray as xr
import linopy
from linopy import Model
from microgridspy.model.parameters import ProjectParameters
from typing import Dict
from linopy import LinearExpression


def add_tes_constraints(
    model: Model,
    settings: ProjectParameters,
    sets: xr.Dataset,
    param: xr.Dataset,
    var: Dict[str, linopy.Variable],
) -> None:
    """
    Add constraints for ice thermal energy storage (TES)
    """
    add_tes_state_of_charge_constraints(model, settings, sets, param, var)
    add_tes_flow_constraints(model, settings, sets, param, var)
    add_tes_production_constraints(model, settings, sets, param, var)


def add_tes_state_of_charge_constraints(
    model: Model,
    settings: ProjectParameters,
    sets: xr.Dataset,
    param: xr.Dataset,
    var: Dict[str, linopy.Variable],
) -> None:

    years = sets.years.values
    periods = sets.periods.values

    first_year = years[0]
    first_period = periods[0]
    last_period = periods[-1]

    # Duration of each time step [h]
    delta_time = float(param["DELTA_TIME"].item())

    # TES capacity [kg]
    tes_capacity = float(param["TES_CAPACITY"].item())

    # Initial SOC as fraction of installed capacity
    tes_initial_soc_fraction = float(param["TES_INITIAL_SOC"].item())

    # Convert storage efficiency into an xarray DataArray
    tes_storage_eff = xr.DataArray(
        settings.tes_params.tes_storage_efficiency,
        dims=["years", "periods"],
        coords={"years": sets.years, "periods": sets.periods},
    )

    # Dynamics of SOC
    for year in years:
        for period in periods:

            soc = var["tes_soc"].sel(years=year, periods=period)
            charge = var["tes_charge"].sel(years=year, periods=period)
            discharge = var["tes_discharge"].sel(years=year, periods=period)

            if year == first_year and period == first_period:
                soc_previous = 0 * soc + tes_capacity * tes_initial_soc_fraction
            elif period == first_period:
                soc_previous = var["tes_soc"].sel(
                    years=year - 1, periods=last_period
                )
            else:
                soc_previous = var["tes_soc"].sel(
                    years=year, periods=period - 1
                )

            model.add_constraints(
                soc ==
                soc_previous * float(tes_storage_eff.sel(years=year, periods=period).item())
                + (charge - discharge) * delta_time,
                name=f"TES State of Charge Constraint - Year {year}, Period {period}",
            )

    # SOC bounds
    for year in years:
        model.add_constraints(
            var["tes_soc"].sel(years=year) <= tes_capacity,
            name=f"TES Maximum Charge Constraint - Year {year}",
        )
        model.add_constraints(
            var["tes_soc"].sel(years=year) >= 0,
            name=f"TES Minimum Charge Constraint - Year {year}",
        )

def add_tes_flow_constraints(
    model: Model,
    settings: ProjectParameters,
    sets: xr.Dataset,
    param: xr.Dataset,
    var: Dict[str, linopy.Variable],
) -> None:
    """
    Constraints for TES charge and discharge mass flow rates.
    """
    years = sets.years.values

    max_charge_rate = param["TES_MAX_CHARGE_RATE"]
    max_discharge_rate = param["TES_MAX_DISCHARGE_RATE"]

    delta_time = float(param["DELTA_TIME"].item())
    tes_capacity = float(param["TES_CAPACITY"].item())

    M_charge = tes_capacity / delta_time
    M_discharge = tes_capacity / delta_time

    for year in years:
        # Upper bounds
        model.add_constraints(
            var["tes_charge"].sel(years=year) <= max_charge_rate,
            name=f"TES Maximum Charge Flow Constraint - Year {year}",
        )
        model.add_constraints(
            var["tes_discharge"].sel(years=year) <= max_discharge_rate,
            name=f"TES Maximum Discharge Flow Constraint - Year {year}",
        )
        # Lower bounds
        model.add_constraints(
            var["tes_charge"].sel(years=year) >= 0,
            name=f"TES Minimum Charge Flow Constraint - Year {year}",
        )
        model.add_constraints(
            var["tes_discharge"].sel(years=year) >= 0,
            name=f"TES Minimum Discharge Flow Constraint - Year {year}",
        )

        for period in sets.periods.values:

            mode = var["tes_mode"].sel(years=year, periods=period)

            # Se mode = 1 può solo caricare
            model.add_constraints(
                var["tes_charge"].sel(years=year, periods=period)
                <= M_charge * mode,
                name=f"TES Charge Allowed - Year {year} Period {period}"
            )

            # Se mode = 0 può solo scaricare
            model.add_constraints(
                var["tes_discharge"].sel(years=year, periods=period)
                <= M_discharge * ((mode * 0 + 1) - mode),
                name=f"TES Discharge Allowed - Year {year} Period {period}"
            )

def add_tes_production_constraints(
    model: Model,
    settings: ProjectParameters,
    sets: xr.Dataset,
    param: xr.Dataset,
    var: Dict[str, linopy.Variable],
) -> None:
    """
    Link ice production to compressor electric consumption via COP and
    specific energy per kg of ice.

    m_prod(t) * Q_per_kg = COP_TES * P_el,TES(t)

    Assumo che tutto il ghiaccio prodotto venga usato per caricare il TES:
    m_charge(t) = m_prod(t)
    """
    tes_cop = param["TES_COP"]
    q_per_kg = param["TES_Q_PER_KG"]

    #produzione ghiaccio e consumo elettrico
    model.add_constraints(
        var["tes_ice_production"] * q_per_kg
        == var["tes_electric_consumption"] * tes_cop,
        name="TES Ice Production Constraint",
    )

    # Il compressore TES non può consumare più della sua capacità installata
    model.add_constraints(
        var["tes_electric_consumption"]
        <= var["tes_compressor_capacity"],
        name="TES Compressor Capacity - Electric Limit"
    )

    #  m_ice_prod <= P_max * COP / Q_per_kg
    max_ice_production = (
        var["tes_compressor_capacity"] * tes_cop / q_per_kg
    )

    # tes ice production bounds
    model.add_constraints(
        var["tes_ice_production"]
        <= max_ice_production,
        name="TES Compressor Capacity - Ice Production Limit"
    )

    # Tutta la produzione va in carica del TES
    model.add_constraints(
        var["tes_charge"] == var["tes_ice_production"],
        name="TES Charge-Production Coupling Constraint",
    )

    # TES compressor capaciy
    model.add_constraints(
        var["tes_compressor_capacity"]
        <= param["TES_COMPRESSOR_CAPACITY_MAX"],
        name="TES Compressor Installed Capacity Limit",
    )
    # Il freddo scaricato non può superare quello prodotto dal compressore TES
    model.add_constraints(
        (var["tes_discharge"] * q_per_kg).sum(dim="periods")
        <=
        (var["tes_electric_consumption"] * tes_cop).sum(dim="periods"),
        name="TES Energy Conservation Constraint",
    )
    
def add_tes_overlap_constraints(
    model: Model,
    settings: ProjectParameters,
    sets: xr.Dataset,
    param: xr.Dataset,
    var: Dict[str, linopy.Variable],
) -> None:
    """
    Penalizzazione della simultaneità tra TES charge e TES discharge.
    Definisce tes_overlap come min(charge, discharge) tramite
    vincoli lineari:
        tes_overlap <= tes_charge
        tes_overlap <= tes_discharge
    """

    years = sets.years.values
    periods = sets.periods.values

    for year in years:
        for period in periods:

            overlap = var["tes_overlap"].sel(years=year, periods=period)
            charge = var["tes_charge"].sel(years=year, periods=period)
            discharge = var["tes_discharge"].sel(years=year, periods=period)

            # tes_overlap <= tes_charge
            model.add_constraints(
                overlap <= charge,
                name=f"TES Overlap Charge Limit - Year {year} Period {period}",
            )

            # tes_overlap <= tes_discharge
            model.add_constraints(
                overlap <= discharge,
                name=f"TES Overlap Discharge Limit - Year {year} Period {period}",
            )
