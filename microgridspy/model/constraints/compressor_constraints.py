from typing import Dict
import xarray as xr
import linopy
from linopy import Model

from microgridspy.model.parameters import ProjectParameters

def add_compressor_constraints(
    model: Model,
    settings: ProjectParameters,
    sets: xr.Dataset,
    param: xr.Dataset,
    var: Dict[str, linopy.Variable],
) -> None:
    """
    Add constraints for the electric compressor.                         
    """

    if not settings.advanced_settings.use_compressor:
        return

    # Relazione COP: Q_cooling = COP * P_electric
    #   compressor_cooling_output = COP_DIRECT * compressor_electric_consumption
    model.add_constraints(
        var["compressor_cooling_output"]
        == param["COP_DIRECT"] * var["compressor_electric_consumption"],
        name="Compressor COP Constraint",
    )

    years = sets.years.values

    for year in years:

        # La potenza termica non può superare la capacità installata
        model.add_constraints(
            var["compressor_cooling_output"].sel(years=year)
            <= var["compressor_capacity"],
            name=f"Compressor Capacity Constraint - Year {year}",
        )
