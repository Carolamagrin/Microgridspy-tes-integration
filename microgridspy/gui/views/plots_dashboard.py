import streamlit as st
import pandas as pd
import os
st.write("PLOTS DASHBOARD FILE:", os.path.abspath(__file__))
from typing import Dict, Any, List
from pathlib import Path
from microgridspy.model.model import Model
from config.path_manager import PathManager
from microgridspy.post_process.cost_calculations import (
    calculate_actualized_investment_cost,
    calculate_actualized_salvage_value,
    calculate_lcoe,
    calculate_grid_costs)
from microgridspy.post_process.energy_calculations import (
    calculate_energy_usage,
    calculate_renewable_penetration,
    calculate_partial_load_indicators)
from microgridspy.post_process.data_retrieval import get_sizing_results, get_conversion_sizing_results
from microgridspy.post_process.plots import (
    costs_pie_chart,
    create_energy_usage_pie_chart,
    dispatch_plot,
    create_sizing_plot
)
from microgridspy.post_process.export_results import save_energy_balance_to_excel, save_plots

# Constants
DEFAULT_COLORS = {
    'Demand': '#000000',  # Black
    'Curtailment': '#FFA500',  # Orange
    'Battery': '#4CC9F0',  # Light Blue
    'Electricity Purchased': '#800080',  # Purple
    'Electricity Sold': '#008000',  # Green
    'Lost Load': '#F21B3F'  # Red
}

# Helper functions
def initialize_colors(model: Model) -> Dict[str, str]:
    """Initialize or retrieve the color dictionary from the session state."""
    colors = DEFAULT_COLORS.copy()

    # Add renewable sources colors
    for i, res_name in enumerate(model.sets['renewable_sources'].values):
        colors[res_name] = ['#FFFF00', '#FFFFE0', '#FFFACD', '#FAFAD2'][i % 4]  # Shades of yellow

    # Add generator types colors if they exist
    if model.has_generator:
        for i, gen_name in enumerate(model.sets['generator_types'].values):
            colors[gen_name] = ['#00509D', '#0066CC', '#0077B6', '#0088A3'][i % 4]  # Shades of blue

    if 'color_dict' not in st.session_state:
        st.session_state.color_dict = colors

    return st.session_state.color_dict

def create_color_customization_section(all_elements: List[str], color_dict: Dict[str, str]) -> None:
    """Create a color customization section in the Streamlit app."""
    st.write("Customize colors for each technology: click on the color picker to change the color.")
    cols = st.columns(len(all_elements))
    for element, col in zip(all_elements, cols):
        with col:
            default_color = color_dict.get(element, DEFAULT_COLORS.get(element))
            color_dict[element] = st.color_picker(
                element,
                key=f"color_{element}",
                value=default_color)

def costs_breakdown(model: Model, optimization_goal: str):
    """Display the cost breakdown of the model."""
    currency = st.session_state.get('currency', 'USD')
    actualized = optimization_goal == "NPC"

    cost_data: List[Dict[str, Any]] = []

    def add_cost_item(label: str, value: float, condition: bool = True):
        if condition:
            cost_data.append({
                "Cost Item": label,
                f"Value (k{currency})": f"{value / 1000:.2f}"})

    # Function to check if a variable exists in the solution
    def get_variable_value(var_name: str, default=0):
        try:
            return model.get_solution_variable(var_name).values.item()
        except ValueError:
            return default

    # Investment Cost
    investment_cost = (get_variable_value("Total Investment Cost") if actualized else calculate_actualized_investment_cost(model))
    add_cost_item("Total Investment Cost (Actualized)", investment_cost)

    # Variable Cost
    variable_cost_label = f"Total Variable Cost ({'Actualized' if actualized else 'Not Actualized'})"
    variable_cost = get_variable_value(f"Scenario Total Variable Cost {'(Actualized)' if actualized else '(Not Actualized)'}")
    add_cost_item(variable_cost_label, variable_cost)

    # Fixed O&M Cost
    om_cost_label = f" - Total Fixed O&M Cost ({'Actualized' if actualized else 'Not Actualized'})"
    om_cost = get_variable_value(f"Operation and Maintenance Cost {'(Actualized)' if actualized else '(Not Actualized)'}")
    add_cost_item(om_cost_label, om_cost)

    # Battery Cost
    if model.has_battery:
        battery_cost_label = f" - Total Battery Replacement Cost ({'Actualized' if actualized else 'Not Actualized'})"
        battery_cost = get_variable_value(f"Battery Replacement Cost {'(Actualized)' if actualized else '(Not Actualized)'}")
        add_cost_item(battery_cost_label, battery_cost)

    # Generator Cost (only if the variable exists)
    if model.has_generator:
        fuel_cost_label = f" - Total Fuel Cost ({'Actualized' if actualized else 'Not Actualized'})"
        fuel_cost = get_variable_value(f"Total Fuel Cost {'(Actualized)' if actualized else '(Not Actualized)'}")
        add_cost_item(fuel_cost_label, fuel_cost, fuel_cost > 0)  # Avoid adding if it's zero

    # Salvage Value
    salvage_value = (get_variable_value("Salvage Value") if actualized else calculate_actualized_salvage_value(model))
    add_cost_item("Total Salvage Value (Actualized)", salvage_value)

    # Grid Costs
    if model.has_grid_connection:
        grid_costs = calculate_grid_costs(model, actualized)
        add_cost_item("Grid Investment Cost (Actualized)", grid_costs[0])
        add_cost_item(f"Grid Fixed O&M Cost ({'Actualized' if actualized else 'Not Actualized'})", grid_costs[1])
        add_cost_item(f"Total Electricity Purchased Cost ({'Actualized' if actualized else 'Not Actualized'})", grid_costs[2])

        if model.get_settings('grid_connection_type', advanced=True) == 1:
            add_cost_item(f"Total Electricity Sold Revenue ({'Actualized' if actualized else 'Not Actualized'})", grid_costs[3])

    # Create DataFrame
    cost_df = pd.DataFrame(cost_data)

    return cost_df


def define_all_elements(model: Model) -> List[str]:
    """Define all possible elements for the energy system."""
    elements = ["Demand", "Curtailment"] + list(model.sets['renewable_sources'].values)
    if model.has_battery:
        elements.append("Battery")
    if model.has_generator:
        elements.extend(list(model.sets['generator_types'].values))
    if model.has_grid_connection:
        elements.append("Electricity Purchased")
        if model.get_settings('grid_connection_type', advanced=True) == 1:
            elements.append("Electricity Sold")
    if model.get_settings('lost_load_fraction') > 0.0:
        elements.append("Lost Load")
    return elements

def plot_tes_charge_discharge(model: Model):
    import matplotlib.pyplot as plt
    import numpy as np
    import streamlit as st

    # Results
    result = model.solution

    # First scenario
    if "scenarios" in result.dims:
        result = result.isel(scenarios=0)

    # Charg flow and Discharge flow [kg/h]
    da_charge = result["TES Charge Flow"].isel(years=0)
    da_discharge = result["TES Discharge Flow"].isel(years=0)

    tes_charge = da_charge.values.flatten()
    tes_discharge = da_discharge.values.flatten()

    # tes net = tes charge - tes discharge
    tes_net = tes_charge - tes_discharge

    hours = len(tes_net)
    days = hours // 24
    if days == 0:
        st.warning("Not enough periods for TES visualization.")
        return

    # SOC
    tes_soc = None

    soc_candidates = [
        "TES State of Charge",
        "TES SOC",
        "TES Energy in Storage",
        "TES Stored Energy",
        "TES Content",
        "TES Mass in Tank",
    ]
    for name in soc_candidates:
        if name in result.data_vars:
            tes_soc = result[name].isel(years=0).values.flatten()
            break

    if tes_soc is None:
        # Δt = 1 h 
        tes_soc = np.cumsum(tes_net)

    selected_day = st.slider("Select start day", 0, days - 1, 0)
    num_days = st.slider("Number of days", 1, min(14, days - selected_day), 1)  # max 14 per leggibilità

    start = selected_day * 24
    end = (selected_day + num_days) * 24
    x = np.arange(24 * num_days)

    tes_net_sel = tes_net[start:end]
    tes_soc_sel = tes_soc[start:end]

    # SOC in % rispetto alla CAPACITÀ reale se ce l’hai, altrimenti normalizzazione locale
    # Se nel result hai già SOC in %, lascialo così.
    # Se è in kg (massa), puoi convertirlo:
    tes_cap = float(model.parameters.get("tes_capacity", 0))  # se esiste
    if tes_cap > 0 and (np.nanmax(tes_soc_sel) > 100):  # euristica: se sembra in kg
        tes_soc_pct = tes_soc_sel / tes_cap * 100.0
    else:
        # fallback: se è già % oppure non sai la capacità
        tes_soc_pct = tes_soc_sel

    fig, ax1 = plt.subplots(figsize=(12, 4))
    ax2 = ax1.twinx()

    ax1.fill_between(x, 0, tes_net_sel, alpha=0.35, label="TES net flow [kg/h]")
    ax1.axhline(0, color="black", linewidth=1)
    ax1.set_xlabel("Hour")
    ax1.set_ylabel("TES net flow [kg/h]")
    ax1.set_title(f"TES Charge/Discharge — Days {selected_day + 1} to {selected_day + num_days}")

    ax2.plot(x, tes_soc_pct, color="black", linewidth=2, label="TES state of charge")
    ax2.set_ylabel("TES state of charge [%]" if tes_cap > 0 else "TES state of charge")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper right")

    st.pyplot(fig)

def plot_tes_and_direct_cooling(model: Model, year: int = 0):
    import matplotlib.pyplot as plt
    import numpy as np
    import streamlit as st

    result = model.solution
    ts = model.time_series

    # TES discharge
    if "TES Discharge Flow" in result:
        tes_discharge = result["TES Discharge Flow"].isel(years=year).values.flatten()
    else:
        tes_discharge = 0

    Q_per_kg = float(model.parameters.get("TES_Q_PER_KG", 0))
    tes_discharge_kw = tes_discharge * Q_per_kg / 1000  # kW_th

    if not getattr(model, "has_tes", False):
        if "THERMAL_DEMAND" in ts:
            n_hours = len(ts["THERMAL_DEMAND"].isel(years=year).values.flatten())
        else:
            st.warning("Cannot infer time dimension for cooling plot.")
            return
        tes_discharge_kw = np.zeros(n_hours)

    # Direct cooling
    if getattr(model, "has_compressor", False) and "compressor_cooling_output" in result:
        dc_th = result["compressor_cooling_output"].isel(years=year).values.flatten()
    else:
        dc_th = np.zeros_like(tes_discharge_kw)
    dc_th_kw = dc_th / 1000

    # Thermal demand
    if "THERMAL_DEMAND" in ts:
        th_kw = ts["THERMAL_DEMAND"].isel(years=year).values.flatten() / 1000
    else:
        th_kw = None

    n_hours = len(dc_th_kw)
    days = n_hours // 24
    if days == 0:
        st.warning("Not enough data for TES visualization.")
        return

    selected_day = st.slider("Select start day for TES + Direct Cooling", 0, days - 1, 0)
    num_days = st.slider("Number of days (TES + Direct)", 1, min(14, days - selected_day), 1)

    start = selected_day * 24
    end = (selected_day + num_days) * 24
    x = np.arange(24 * num_days)

    tes_sel = tes_discharge_kw[start:end]
    dc_sel = dc_th_kw[start:end]
    total_sel = tes_sel + dc_sel
    th_sel = th_kw[start:end] if th_kw is not None else None

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.fill_between(x, 0, tes_sel, alpha=0.35, label="TES Discharge [kW_th]")
    ax.fill_between(x, tes_sel, tes_sel + dc_sel, alpha=0.35, label="Direct Cooling [kW_th]")

    if th_sel is not None:
        ax.plot(x, th_sel, 'k--', linewidth=2, label="Thermal Demand")

    ax.plot(
        x,
        total_sel,
        linewidth=3,
        color="green",
        label="Cooling Supplied (TES+Direct)"
    )

    ax.set_xlabel("Hour")
    ax.set_ylabel("Cooling [kW_th]")
    ax.set_title(f"TES + Direct Cooling — Days {selected_day + 1} to {selected_day + num_days}")
    ax.legend()
    ax.grid(True)

    st.pyplot(fig)

def export_results(project_name: str, model: Model, costs_df: pd.DataFrame, sizing_df: pd.DataFrame, conversion_sizing_df: pd.DataFrame, fig: dict) -> None:
    """Setup the export results section."""

    # Retrieve results folder path
    results_folder = Path(PathManager.RESULTS_FOLDER_PATH)
    plots_folder = results_folder / "Plots"
    plots_folder.mkdir(exist_ok=True)

    # Retrieve the related project folder path
    path_manager = PathManager(project_name)
    project_folder = Path(path_manager.PROJECTS_FOLDER_PATH) / project_name / "results"
    project_folder_plots = project_folder / "Plots"
    project_folder_plots.mkdir(exist_ok=True, parents=True)

    if st.button("📁 Export Results to Excel"):
        with st.spinner("Exporting results..."):
            # Cost breakdown
            costs_df.to_excel(results_folder / "Costs Breakdown.xlsx", index=False)
            costs_df.to_excel(project_folder / "Costs Breakdown.xlsx", index=False)
            
            # Sizing results
            sizing_df.to_excel(results_folder / "Sizing Results.xlsx", index=False)
            sizing_df.to_excel(project_folder / "Sizing Results.xlsx", index=False)
            if conversion_sizing_df is not None:
                conversion_sizing_df.to_excel(results_folder / "Conversion Sizing Results.xlsx", index=False)
                conversion_sizing_df.to_excel(project_folder / "Conversion Sizing Results.xlsx", index=False)
            
            # Energy balance
            save_energy_balance_to_excel(model, results_folder)
            save_energy_balance_to_excel(model, project_folder)
        
        st.success(f"Results exported successfully to {results_folder} and {project_folder}")

    if st.button("📊 Save Current Plots"):
        with st.spinner("Saving current plots..."):
            save_plots(plots_folder, fig)
            save_plots(project_folder_plots, fig)
        
        st.success(f"Plots saved successfully to {plots_folder} and {project_folder_plots}")


def plots_dashboard():
    """Create the results dashboard with cost breakdown, sizing results, and additional visualizations."""
    fig: dict = {}
    st.title("Results Dashboard")

    if 'model' not in st.session_state:
        st.warning("Please run the optimization model first.")
        return

    model: Model = st.session_state.model
    st.write("Solution variables:", list(model.solution.data_vars))
    currency = st.session_state.get('currency', 'USD')
    project_name = st.session_state.get('project_name')
    num_years = len(model.sets['years'])

    # Optional selector for Pareto exploration
    if 'pareto_front' in st.session_state and 'multiobjective_solutions' in st.session_state:
        st.subheader("Explore Pareto Solutions")

        # Extract front and reverse order for intuitive display (low CO2 first)
        co2_vals, npc_vals = zip(*st.session_state.pareto_front)
        reversed_indices = list(reversed(range(len(co2_vals))))

        # Selectbox displays Solution 1 as lowest CO2, last as highest
        selected_reversed_index = st.selectbox(
            "Select a solution to visualize",
            reversed_indices,
            index=st.session_state.get('selected_solution_index', 0),
            format_func=lambda i: f"Solution {len(co2_vals) - i}: CO₂ = {co2_vals[i]/1000:.2f} t, NPC = {npc_vals[i]/1000:.2f} k{currency}",
            key="selected_solution_index"
        )

        # Map back to original solution index (+2 offset)
        selected_solution_index = selected_reversed_index + 2
        st.session_state.model.solution = st.session_state.multiobjective_solutions[selected_solution_index]


    color_dict = initialize_colors(model)

    # Cost Breakdown
    st.header("Cost Breakdown")

    # Determine the optimization goal
    optimization_goal = 'NPC' if model.get_settings('optimization_goal') == 0 else 'Total Variable Cost'
    actualized = optimization_goal == "NPC"

    # Display main metrics
    main_cost = (
        model.get_solution_variable('Net Present Cost').values.item()
        if actualized else
        model.get_solution_variable('Total Variable Cost').values.item())

    col1, col2 = st.columns(2)
    with col1:
        st.metric(optimization_goal, f"{main_cost / 1000:.2f} k{currency}")

    with col2:
        lcoe = calculate_lcoe(model, optimization_goal)
        lcoe_label = "Levelized Cost of Energy Production (LCOE)" if actualized else "Levelized Variable Cost of Energy Production (LVC)"
        st.metric(lcoe_label, f"{lcoe:.4f} {currency}/kWh")
    
    # COMPRESSOR PERFORMANCE

    if model.has_compressor:
        st.subheader("Compressor Performance")

        # COP
        try:
            cop_value = float(model.parameters["COMPRESSOR_COP"].item())
            st.metric("Compressor COP", f"{cop_value:.2f}")
        except Exception:
            st.metric("Compressor COP", "N/A")

        # Annual electricity consumption
        try:
            comp_kWh = float(model.get_solution_variable("compressor_electric_consumption").sum().item())
            st.metric("Annual Compressor Electricity Use", f"{comp_kWh:.1f} kWh")
        except Exception:
            st.metric("Annual Compressor Electricity Use", "N/A")

    # Display cost breakdown
    st.subheader("Cost Details")
    costs_df = costs_breakdown(model, optimization_goal)
    st.table(costs_df)

    # Cost Breakdown Pie Chart
    cost_breakdown_fig = costs_pie_chart(model, optimization_goal, color_dict)
    fig['Cost Breakdown Bar of Pie Chart'] = cost_breakdown_fig
    st.pyplot(cost_breakdown_fig)

    st.write("---")  # Add a separator

    # Sizing and Dispatch
    st.header("Sizing and Dispatch")
    # Color customization
    all_elements = define_all_elements(model)
    create_color_customization_section(all_elements, color_dict)

    # Sizing results
    st.header("Mini-Grid Sizing")
    sizing_df = get_sizing_results(model)
    sizing_fig = create_sizing_plot(model, color_dict, sizing_df)
    fig['System Sizing'] = sizing_fig
    st.pyplot(sizing_fig)
    st.table(sizing_df)

    conversion_sizing_df = get_conversion_sizing_results(model)
    st.markdown("Conversion Sizing Results")
    st.table(conversion_sizing_df)

    
    # Energy Balance Visualization
    st.header("Energy Usage Visualization")

    st.header("Cooling Visualization")
    
    plot_type = st.selectbox(
        "Select Cooling Plot",
        ["TES Charge/Discharge", "TES + Direct Cooling"] if model.has_tes else ["Direct Cooling Only"]
    )

    if plot_type == "Direct Cooling Only":
        plot_tes_and_direct_cooling(model)

    if plot_type == "TES Charge/Discharge":
        plot_tes_charge_discharge(model)

    elif plot_type == "TES + Direct Cooling":
        plot_tes_and_direct_cooling(model)

    years = [int(year) for year in model.sets['years']]
    min_year, max_year = min(years), max(years)

    # Dispatch Plot
    st.subheader("Dispatch Plot")
    st.info("**Note:** The dispatch plot presented here shows an optimal use of energy based on perfect foresight. It represents an idealized scenario and does not reflect a realistic dispatch strategy with real-time constraints.")
    if len(years) > 1:
        selected_year = st.slider("Select Year for Dispatch Plot", min_value=min_year, max_value=max_year, value=min_year)
        selected_year_index = years.index(selected_year)
        selected_day = st.slider("Select Starting Day", 0, 364, 0, key="day_slider")
    else:
        selected_year_index = 0
        selected_day = st.slider("Select Starting Day", 0, 364, 0, key="day_slider")

    # Add a slider to show hoow many days to show in the dispatch plot
    days_to_show = st.slider("Select Days to Show", 1, 7, 1, key="days_to_show_slider")

    dispatch_fig = dispatch_plot(model, scenario=0, year=selected_year_index, day=selected_day, num_days=days_to_show, color_dict=color_dict)
    if isinstance(dispatch_fig, tuple):
        dispatch_fig = dispatch_fig[0]
    fig['Dispatch Plot'] = dispatch_fig
    st.pyplot(dispatch_fig)

    # Energy Usage Pie Chart
    energy_usage = calculate_energy_usage(model)
    renewable_penetration = calculate_renewable_penetration(model)
    st.subheader("Average Energy Usage")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Average Yearly Curtailment", f"{energy_usage['Curtailment']:.2f}%")
    with col2:
        st.metric("Average Yearly Renewable Penetration", f"{renewable_penetration:.2f}%")

    if model.has_generator:
        energy_usage_fig = create_energy_usage_pie_chart(energy_usage, model, st.session_state.res_names, color_dict, st.session_state.gen_names)
    else:
        energy_usage_fig = create_energy_usage_pie_chart(energy_usage, model, st.session_state.res_names, color_dict)
    fig['Energy Usage Pie Chart'] = energy_usage_fig
    st.pyplot(energy_usage_fig)

    if model.has_generator:
        fuel_consumption_da = model.get_solution_variable('Generator Fuel Consumption')
        fuel_consumption = fuel_consumption_da.sum().item() / num_years # Average yearly fuel consumption
        fuel_consumption = fuel_consumption / 1000  # Convert to kiloliters
        st.metric("Average Yearly Fuel Consumption", f"{fuel_consumption:.2f} kiloliters")

        # Compute and display the Partial Load Indicators
        avg_load_factor, avg_efficiency = calculate_partial_load_indicators(model)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Average Generator Load Factor", f"{avg_load_factor:.2f} %")
        with col2:
            st.metric("Average Generator Efficiency", f"{avg_efficiency:.2f} kWh/liter")

    # Emissions Breakdown (only for multi-objective runs)
    if 'multiobjective_solutions' in st.session_state:
        st.header("Emissions Breakdown")

        total_emission = model.get_solution_variable("Total CO2 Emissions").item()
        st.metric("Total CO₂ Emissions", f"{total_emission / 1000:.2f} tonCO₂")

        data = []

        def add_emission_row(label, var_name):
            try:
                val = model.get_solution_variable(var_name).sum().item()
                if val > 0:
                    data.append({"Emission Source": label, "Value (kgCO₂)": f"{val:.2f}"})
                else:
                    data.append({"Emission Source": label, "Value (kgCO₂)": "0.00"})
            except:
                pass

        add_emission_row("Renewables Installation (LCA)", "CO2 Emissions for Unit of Renewables Installed Capacity")
        if model.has_battery:
            add_emission_row("Battery Installation (LCA)", "Battery Emissions")
        if model.has_generator:
            add_emission_row("Generator Installation (LCA)", "Generator Emissions")
            add_emission_row("Generator Fuel Combustion", "Fuel Emissions")
        if model.has_grid_connection:
            add_emission_row("Grid Import", "Grid Emissions")

        emission_df = pd.DataFrame(data)
        st.table(emission_df)


    # Export results
    st.header("Export Results")
    st.write("Click the buttons below to export the full results to Excel or save the current plots.")
    export_results(project_name, model, costs_df, sizing_df, conversion_sizing_df, fig)

    st.write("---")  # Add a separator

    col1, col2 = st.columns([1, 8])
    with col1:
        if st.button("Back"):
            st.session_state.page = "Optimization"
            st.rerun()
    with col2:
        if st.button("Next"):
            st.session_state.page = "Project Profitability"
            st.rerun()
