import streamlit as st

def cooling_technology():
    st.title("Cooling Technologies Configuration")
    st.write("Configure cooling options: direct compressor cooling and/or TES with compressor.")

    # Carico il modello dei parametri
    data = st.session_state.default_values

    #Selezione tecnologie (TES e Compressore diretto)
    st.subheader("Select Cooling Technologies")

    # Flag: attiva/disattiva TES
    use_tes = st.checkbox(
        "Enable TES (Thermal Energy Storage)",
        value=data.advanced_settings.use_tes,
        help="Enable ice-based TES with its own compressor."
    )
    data.advanced_settings.use_tes = use_tes

    # Flag: attiva/disattiva compressore diretto
    use_compressor = st.checkbox(
        "Enable Direct Cooling Compressor",
        value=data.advanced_settings.use_compressor,
        help="Enable classic vapor-compression cooling."
    )
    data.advanced_settings.use_compressor = use_compressor

    st.markdown("---")

    #Parametri TES 
    if use_tes:
        st.subheader("TES (Thermal Energy Storage) Parameters")

        tes = data.tes_params

        tes.tes_specific_investment_cost = st.number_input(
            "TES Specific Investment Cost [€/kg ice capacity]",
            min_value=0.0,
            value=tes.tes_specific_investment_cost,
            help="Cost per kg of TES storage (ice capacity)."
        )

        tes.tes_specific_om_cost = st.number_input(
            "TES O&M Cost [€/kg/year]",
            min_value=0.0,
            value=tes.tes_specific_om_cost,
            help="Annual O&M cost per kg of TES."
        )

        tes.tes_lifetime = st.number_input(
            "TES Lifetime [years]",
            min_value=1,
            value=tes.tes_lifetime,
            help="Operational lifetime of the TES tank."
        )

        st.markdown("### TES Compressor Parameters")

        tes.tes_compressor_specific_investment_cost = st.number_input(
            "TES Compressor Investment Cost [€/kW_cool]",
            min_value=0.0,
            value=tes.tes_compressor_specific_investment_cost,
            help="Cost per kW of TES compressor capacity."
        )

        tes.tes_compressor_specific_om_cost = st.number_input(
            "TES Compressor O&M Cost [€/kW/year]",
            min_value=0.0,
            value=tes.tes_compressor_specific_om_cost,
            help="Annual O&M per kW of TES compressor."
        )

        tes.tes_compressor_lifetime = st.number_input(
            "TES Compressor Lifetime [years]",
            min_value=1,
            value=tes.tes_compressor_lifetime,
            help="Operational lifetime of TES compressor."
        )

        tes.tes_cop = st.number_input(
            "TES COP [-]",
            min_value=0.1,
            value=tes.tes_cop,
            help="Coefficient of Performance of the TES compressor."
        )

        tes.tes_max_charge_rate = st.number_input(
            "Max Charge Rate [kg/h]",
            min_value=0.0,
            value=tes.tes_max_charge_rate,
            help="Maximum amount of ice that can be produced per hour."
        )

        tes.tes_max_discharge_rate = st.number_input(
            "Max Discharge Rate [kg/h]",
            min_value=0.0,
            value=tes.tes_max_discharge_rate,
            help="Maximum amount of cooling extracted per hour."
        )

        tes.tes_capacity = st.number_input(
            "TES Capacity [kg of ice]",
            min_value=0.0,
            value=tes.tes_capacity,
            help="Total ice mass the TES tank can store."
        )

        tes.tes_initial_soc = st.number_input(
            "Initial State of Charge [-]",
            min_value=0.0,
            max_value=1.0,
            value=tes.tes_initial_soc,
            help="Initial fraction of TES capacity filled with ice (0 = vuoto, 1 = pieno)."
        )

        tes.tes_storage_efficiency = st.number_input(
            "Storage Efficiency per timestep [-]",
            min_value=0.0,
            max_value=1.0,
            value=tes.tes_storage_efficiency,
            help="Fraction of TES charge that remains from one timestep to the next."
        )

        tes.tes_q_per_kg = st.number_input(
            "Cooling per kg of ice [Wh/kg]",
            min_value=0.0,
            value=tes.tes_q_per_kg,
            help="Cooling energy provided per kg of ice (latente + eventuale sensibile)."
        )

        st.success("TES parameters updated.")

        st.markdown("---")

    # Parametri compressore diretto
    if use_compressor:
        st.subheader("Direct Cooling Compressor Parameters")

        comp = data.compressor_params

        comp.compressor_specific_investment_cost = st.number_input(
            "Specific Investment Cost [€/kW_cool]",
            min_value=0.0,
            value=comp.compressor_specific_investment_cost,
            help="Cost per kW of cooling capacity installed."
        )

        comp.compressor_specific_om_cost = st.number_input(
            "Specific O&M Cost [€/kW_cool/year]",
            min_value=0.0,
            value=comp.compressor_specific_om_cost,
            help="Annual O&M cost per kW of cooling capacity."
        )

        comp.compressor_lifetime = st.number_input(
            "Lifetime [years]",
            min_value=1,
            value=comp.compressor_lifetime,
            help="Expected lifetime of the direct cooling compressor."
        )

        st.success("Direct compressor parameters updated.")

    st.markdown("---")

    col1, col2 = st.columns([1, 8])

    with col1:
        if st.button("Back"):
            st.session_state.page = "Demand Assessment"
            st.rerun()

    with col2:
        if st.button("Next"):
            st.session_state.page = "Renewables Characterization"
            st.rerun()
