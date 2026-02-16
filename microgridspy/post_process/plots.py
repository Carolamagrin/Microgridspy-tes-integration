import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

from typing import Dict

from microgridspy.model.model import Model
from microgridspy.post_process.cost_calculations import get_cost_details


def costs_pie_chart(model: Model, optimization_goal: str, color_dict: Dict[str, str]):
    cost_details = get_cost_details(model, optimization_goal)
    actualized = optimization_goal == "NPC"
    suffix = "(Actualized)" if actualized else "(Not Actualized)"

    if actualized:
        total_investment_cost = cost_details[f"Total Investment Cost (Actualized)"] 
        scenario_total_variable_cost = cost_details[f"Total Variable Cost {suffix}"]
        total_salvage_value = cost_details[f"Total Salvage Value (Actualized)"]
    else:
        total_investment_cost = cost_details[f"Total Investment Cost (Actualized)"] / 1000 # Convert to kUSD
        scenario_total_variable_cost = cost_details[f"Total Variable Cost {suffix}"]
        total_salvage_value = cost_details[f"Total Salvage Value (Actualized)"] / 1000 # Convert to kUSD
    

    total_cost = total_investment_cost + scenario_total_variable_cost

    # Prepare data for pie chart using color_dict
    pie_data = [
        ("Total Investment Cost", total_investment_cost, color_dict.get("Investment", '#ff9999')),
        ("Total Variable Cost", scenario_total_variable_cost, color_dict.get("Variable", '#66b3ff'))
    ]

    # Calculate percentages for pie chart
    labels, sizes, colors = zip(*[(label, (value / total_cost) * 100, color) for label, value, color in pie_data])

    # Prepare data for bar chart using color_dict
    variable_data = [
        ("Fixed O&M", cost_details[f"Total Fixed O&M Cost {suffix}"], color_dict.get("Fixed O&M", '#ffcc99')),
        ("Battery Replacement", cost_details.get(f"Total Battery Replacement Cost {suffix}", 0), color_dict.get("Battery", '#ff6666')),
        ("Fuel Cost", cost_details.get(f"Total Fuel Cost {suffix}", 0), color_dict.get("Fuel", '#c2c2f0')),
        ("Electricity Cost", cost_details.get(f"Total Electricity Purchased Cost {suffix}", 0), color_dict.get("Electricity Purchased", '#98FB98'))
    ]

    # Filter out zero-cost items
    variable_data = [(label, value, color) for label, value, color in variable_data if value > 0]
    variable_labels, variable_costs, variable_colors = zip(*variable_data) if variable_data else ([], [], [])
    variable_percentages = [cost / scenario_total_variable_cost * 100 for cost in variable_costs] if scenario_total_variable_cost > 0 else []

    # Create the figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={'width_ratios': [1.5, 1]})
    fig.suptitle(f"Cost Breakdown (%) - {optimization_goal}", fontsize=16)

    # Pie chart
    wedges, texts, autotexts = ax1.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    ax1.axis('equal')

    # Add Salvage Value as text
    salvage_percentage = (total_salvage_value / total_cost) * 100
    ax1.text(0, -1.2, f"Salvage Value: {salvage_percentage:.1f}%", ha='center', va='center', fontweight='bold')

    # Bar chart for variable costs breakdown
    if variable_costs:
        y_pos = range(len(variable_labels))
        ax2.barh(y_pos, variable_percentages, align='center', color=variable_colors)
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(variable_labels)
        ax2.invert_yaxis()  # Labels read top-to-bottom
        ax2.set_xlabel('Percentage (%)')
        ax2.set_title('Breakdown of Variable Costs')

        # Add percentage values to the end of each bar
        for i, v in enumerate(variable_percentages):
            ax2.text(v, i, f' {v:.1f}%', va='center')
    else:
        ax2.text(0.5, 0.5, "No variable costs", ha='center', va='center')
        ax2.axis('off')

    # Adjust layout
    plt.tight_layout()

    return fig

def create_sizing_plot(model: Model, color_dict: dict, sizing_df: pd.DataFrame):
    """
    Create a bar plot to visualize existing and total capacities.
    The existing capacity section will be displayed with a distinct, darker color.
    """
    # Extract data from sizing_df
    categories = sizing_df['Component'].tolist()
    existing_capacities = sizing_df['Existing'].astype(int).values
    total_capacities = sizing_df['Total'].astype(int).values

    # Assign colors from the color dictionary
    colors = [color_dict.get(cat.split(' (')[0], '#000000') for cat in categories]  # Default to black if not found

    # Define colors for existing and new capacities
    existing_colors = colors  # Original colors for existing capacities
    new_colors = [color + 'AA' if isinstance(color, str) and color.startswith('#') else color for color in colors]  # Lighter shade for new capacity

    # Create the bar plot
    fig, ax = plt.subplots(figsize=(10, 5))

    # Plot existing capacities with the original color
    ax.bar(categories, existing_capacities, color=existing_colors, label='Existing Capacity')  # Full color

    # Plot the additional capacities using a lighter shade
    ax.bar(categories, total_capacities - existing_capacities, color=new_colors, bottom=existing_capacities, label='New Capacity')  # Lighter shade

    # Customize the plot
    ax.set_ylabel('Capacity')
    ax.set_title('System Sizing')
    plt.tight_layout()

    return fig


def dispatch_plot(model: Model, scenario: int, year: int, day: int, num_days: int, color_dict: dict):
    """
    Plot the energy balance for a given day and year, including grid interactions and curtailment
    DEMAND + compressor_electric_consumption + tes_electric_consumption.
    """

    import numpy as np
    import matplotlib.pyplot as plt
    
    print("time_series vars:", list(model.time_series.data_vars))

    # Datas
    result = model.solution

    demand = model.parameters['DEMAND']                            # [Wh]
    res_production = model.get_solution_variable('Energy Production by Renewables')
    curtailment = model.get_solution_variable('Curtailment by Renewables')
    battery_inflow = model.get_solution_variable('Battery Inflow') if model.has_battery else None
    battery_outflow = model.get_solution_variable('Battery Outflow') if model.has_battery else None
    generator_production = model.get_solution_variable('Generator Energy Production') if model.has_generator else None
    energy_from_grid = model.get_solution_variable('Energy from Grid') if model.has_grid_connection else None
    energy_to_grid = model.get_solution_variable('Energy to Grid') if model.has_grid_connection and model.get_settings('grid_connection_type', advanced=True) == 1 else None
    lost_load = model.get_solution_variable('Lost Load') if model.get_settings('lost_load_fraction') > 0.0 else None

    start_idx = day * 24
    end_idx = (day + num_days) * 24
    x = range(24 * num_days)

    # Theoretical electric demand from thermal load ---
    thermal_el_demand = None

    if "THERMAL_DEMAND" in model.time_series.data_vars:
        thermal_demand_th = (
            model.time_series["THERMAL_DEMAND"]
            .isel(years=year)[start_idx:end_idx]
            / 1000.0  # kWh_th
        )

        if "COMPRESSOR_COP" in model.parameters:
            cop = float(model.parameters["COMPRESSOR_COP"])
            if cop > 0:
                thermal_el_demand = thermal_demand_th / cop

    steps = model.sets['steps'].values
    years = model.sets['years'].values
    step_duration = model.settings.advanced_settings.step_duration
    years_steps_tuples = [(years[i] - years[0], steps[i // step_duration]) for i in range(len(years))]
    year_to_step = {y: s for (y, s) in years_steps_tuples}
    step = year_to_step[year]

    # (DEMAND)
    base_el = demand.isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0  # kWh

    # electric consumption of compressor
    try:
        comp_da = model.get_solution_variable("Compressor Electric Consumption")
    except Exception:
        comp_da = result.get("compressor_electric_consumption", None)

    if comp_da is not None:
        comp_el = comp_da.isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
    else:
        comp_el = np.zeros_like(base_el)

    # TES elctric consumption
    try:
        tes_da = model.get_solution_variable("TES Electric Consumption")
    except Exception:
        tes_da = result.get("tes_electric_consumption", None)

    if tes_da is not None:

        # controllo scenario
        dims = tes_da.dims

        if "scenarios" in dims:
            tes_el = tes_da.isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
        else:
            tes_el = tes_da.isel(years=year)[start_idx:end_idx] / 1000.0

    else:
        tes_el = np.zeros_like(base_el)

    # total electric demand
    dispatch_demand = base_el + comp_el + tes_el   # kWh

    print("DISPATCH DEBUG")
    print("base_el max:", float(base_el.max()))
    print("comp_el max:", float(comp_el.max()))
    print("tes_el max:", float(tes_el.max()))
    print("dispatch_demand max:", float(dispatch_demand.max()))

    daily_battery_inflow = (
        battery_inflow.isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
        if battery_inflow is not None else np.zeros_like(dispatch_demand)
    )
    daily_battery_outflow = (
        battery_outflow.isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
        if battery_outflow is not None else np.zeros_like(dispatch_demand)
    )
    daily_energy_from_grid = (
        energy_from_grid.isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
        if energy_from_grid is not None else np.zeros_like(dispatch_demand)
    )
    daily_energy_to_grid = (
        energy_to_grid.isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
        if energy_to_grid is not None else np.zeros_like(dispatch_demand)
    )
    daily_lost_load = (
        lost_load.isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
        if lost_load is not None else np.zeros_like(dispatch_demand)
    )
    daily_total_curtailment = (
        curtailment.sum('renewable_sources').isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
        if curtailment is not None else np.zeros_like(dispatch_demand)
    )

    fig, ax = plt.subplots(figsize=(20, 12))

    cumulative_outflow = np.zeros(24 * num_days)
    cumulative_inflow = np.zeros(24 * num_days)

    # Plot actual renewable energy production for each source
    renewable_sources = model.sets['renewable_sources'].values
    for source in renewable_sources:
        daily_source_production = (
            res_production.sel(renewable_sources=source, steps=step)
            .isel(scenarios=scenario)[start_idx:end_idx] / 1000.0
        )
        daily_source_curtailment = (
            curtailment.sel(renewable_sources=source)
            .isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
            if curtailment is not None else 0.0
        )
        daily_actual_production = daily_source_production - daily_source_curtailment
        ax.fill_between(
            x, cumulative_outflow, cumulative_outflow + daily_actual_production,
            label=f'{source} Actual Production',
            color=color_dict.get(source), alpha=0.5
        )
        cumulative_outflow += daily_actual_production

    # Plot battery charging and discharging
    ax.fill_between(
        x, -cumulative_inflow, -(cumulative_inflow + daily_battery_inflow),
        label='Battery Charging', color=color_dict.get('Battery'), alpha=0.5
    )
    cumulative_inflow += daily_battery_inflow

    ax.fill_between(
        x, cumulative_outflow, cumulative_outflow + daily_battery_outflow,
        label='Battery Discharging', color=color_dict.get('Battery'), alpha=0.5
    )
    cumulative_outflow += daily_battery_outflow

    #  Plot energy from grid
    if energy_from_grid is not None:
        ax.fill_between(
            x, cumulative_outflow, cumulative_outflow + daily_energy_from_grid,
            label='Energy from Grid', color=color_dict.get('Electricity Purchased'), alpha=0.5
        )
        cumulative_outflow += daily_energy_from_grid

    # Plot generator production for each type
    if generator_production is not None:
        generator_types = generator_production.coords['generator_types'].values
        for gen_type in generator_types:
            daily_gen_production = (
                generator_production.sel(generator_types=gen_type)
                .isel(years=year, scenarios=scenario)[start_idx:end_idx] / 1000.0
            )
            ax.fill_between(
                x, cumulative_outflow, cumulative_outflow + daily_gen_production,
                label=f'{gen_type} Production', color=color_dict.get(gen_type), alpha=0.5
            )
            cumulative_outflow += daily_gen_production

    # Plot Lost Load
    if lost_load is not None:
        ax.fill_between(
            x, cumulative_outflow, cumulative_outflow + daily_lost_load,
            label='Lost Load', color=color_dict.get('Lost Load'), alpha=0.5
        )
        cumulative_outflow += daily_lost_load

    #  Plot energy to grid (as negative values)
    if energy_to_grid is not None:
        ax.fill_between(
            x, -cumulative_inflow, -(cumulative_inflow + daily_energy_to_grid),
            label='Energy to Grid', color=color_dict.get('Electricity Sold'), alpha=0.5
        )
        cumulative_inflow += daily_energy_to_grid

    # eletrcic demand
    ax.plot(
        x, dispatch_demand,
        label='Cooling System Electric Consumption',
        color=color_dict.get('Demand', 'black'),
        linewidth=3
    )
    
    ax2 = ax.twinx()

    # Theoretical electric demand from thermal load
    if thermal_el_demand is not None:
        ax2.plot(
            x,
            thermal_el_demand,
            linestyle='--',
            color='red',
            linewidth=3,
            label='Thermal Demand / COP (Theoretical)'
        )

        ax2.set_ylim(0, 1.2 * max(thermal_el_demand))
        ax2.tick_params(axis='y', labelcolor='red')
        ax2.set_ylabel('Theoretical Cooling Electric Demand (kWh)')

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=14)

    # Curtailment
    ax.fill_between(
        x, cumulative_outflow, cumulative_outflow + daily_total_curtailment,
        label='Curtailment', color=color_dict.get('Curtailment'), alpha=0.5
    )

    ax.set_xlabel('Hours')
    ax.set_ylabel('Energy (kWh)')
    ax.set_title(f'Energy Balance (Cooling Demand) - Year {year + 1}, Day {day + 1}', fontsize=20)
    ax.legend(loc='upper left', fontsize=14, framealpha=0.8)
    ax.grid(True)

    y_min = min(ax.get_ylim()[0], -daily_energy_to_grid.max() if energy_to_grid is not None else 0)
    y_max = max(ax.get_ylim()[1], dispatch_demand.max())
    ax.set_ylim(bottom=y_min, top=y_max)

    return fig, {
        "base_el_max": float(base_el.max()),
        "comp_el_max": float(comp_el.max()),
        "tes_el_max": float(tes_el.max()),
        "dispatch_demand_max": float(dispatch_demand.max())
    }

def create_energy_usage_pie_chart(energy_usage: dict, model: Model, res_names, color_dict, gen_names=None):
    """Create a pie chart of energy usage percentages with a legend and external labels."""
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Dynamically create color mapping and usage data
    color_mapping = {}
    usage_data = {}
    
    # Add renewable sources
    for res in res_names:
        color_mapping[f"{res} Usage"] = res
        usage_data[f"{res} Usage"] = energy_usage.get(f"{res} Usage", 0)

    # Add Battery
    if model.has_battery:
        color_mapping["Battery Usage"] = "Battery"
        usage_data["Battery Usage"] = energy_usage.get("Battery Usage", 0)
    
    # Add generators
    if model.has_generator:
        for gen in gen_names:
            color_mapping[f"{gen} Usage"] = gen
            usage_data[f"{gen} Usage"] = energy_usage.get(f"{gen} Usage", 0)

    if model.has_grid_connection:
        color_mapping["Grid Usage"] = "Electricity Purchased"
        usage_data["Grid Usage"] = energy_usage.get("Grid Usage", 0)

    # Remove zero values
    usage_data = {k: v for k, v in usage_data.items() if v > 0}
    
    # Get colors based on the mapping
    colors = [color_dict.get(color_mapping.get(k, k)) for k in usage_data.keys()]
    
    wedges, texts, autotexts = ax.pie(usage_data.values(), 
                                      colors=colors,
                                      autopct=lambda pct: f'{pct:.1f}%',
                                      pctdistance=0.8,
                                      wedgeprops=dict(width=0.5))
    
    # Add labels outside the pie chart
    ax.legend(wedges, usage_data.keys(),
              title="Energy Usage",
              loc="center left",
              bbox_to_anchor=(1, 0, 0.5, 1))
    
    ax.set_title('Average Energy Usage by Technology')
    
    # Remove bold formatting from percentage labels
    plt.setp(autotexts, weight="normal", size=8)
    
    plt.tight_layout()
    
    return fig