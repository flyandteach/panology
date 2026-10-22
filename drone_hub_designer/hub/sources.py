"""Sources behind the reference aircraft library.

These figures were gathered from web search results in October 2026. This
environment could not open the FAA PDFs or manufacturer pages directly, so
every figure is a quoted excerpt, not a value checked against the full
document. Open the source before relying on a number.
"""

SOURCES = {
    # FAA environmental assessments (primary)
    "faa_wing_houston_draft": ("FAA Draft EA, Wing Houston (May 2026)",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/20260504_Full_Draft_EA_Wing_Houston_for_Publication_Compiled.pdf"),
    "faa_wing_houston_final": ("FAA Final EA, Wing Houston (Aug 2026)",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/20260813_Final_EA_Wing_Houston_ADA_Signed.pdf"),
    "faa_wing_dfw_sea": ("FAA Final Supplemental EA, Wing Dallas-Fort Worth (Apr 2025)",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/20250421_Wing_DFW_Final_SEA_Combined.pdf"),
    "faa_wing_cfl": ("FAA Final EA, Wing Central Florida (Jun 2025)",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/06272025_Final_EA_Wing_Central_Florida.pdf"),
    "faa_zipline_dfw": ("FAA Final EA, Zipline Dallas-Fort Worth (Dec 2025)",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/20251223_Zipline_Final_DFW_EA_508_signed.pdf"),
    "faa_zipline_pea_ridge": ("FAA Reevaluation, Zipline Pea Ridge AR (Feb 2026)",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/Zipline_Pea_Ridge_AR_Reevaluation_20260220_Signed.pdf"),
    "faa_amz_chicago_d": ("FAA EA Appendix D, Amazon Chicago",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/AMZ-CHICAGO-Appendix_D-1.pdf"),
    "faa_amz_pendleton": ("FAA Written Re-evaluation, Amazon Pendleton OR (Aug 2025)",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/20250827_Amazon_Pendleton_OR_Written_ReEvaluation.pdf"),
    "faa_amz_tpa": ("FAA Draft EA, Amazon Tampa",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/AMZ_TPA_Draft_EA_Report.pdf"),
    "faa_amz_fla_final": ("FAA Final EA / ROD, Amazon Florida",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/AMZ-FLA-Final-EA-ADA-508-FINAL-signed.pdf"),
    "faa_amz_omaha": ("FAA Final EA, Amazon Omaha NE",
        "https://www.faa.gov/uas/advanced_operations/nepa_and_drones/Amazon_Omaha_NE_Final_EA_ADA_508_Final_Signed.pdf"),
    # Manufacturer
    "wing_how_drones_work": ("Wing, How do drones work (2021)",
        "https://wing.com/resource-hub/articles/how-do-drones-work"),
    "flytrex_lc_pr": ("Flytrex / Little Caesars press release (Apr 2026)",
        "https://www.businesswire.com/news/home/20260423234109/en/In-a-First-for-Drone-Delivery-Flytrex-and-Little-Caesars-Can-Now-Deliver-Two-Large-Pizzas-to-Your-Door"),
    # Press and trackers (secondary)
    "dronexl_aircraft": ("DroneXL delivery aircraft comparison (FAA-table based)",
        "https://dronexl.co/tracker/drone-delivery/aircraft/"),
    "dronexl_zipline": ("DroneXL Zipline operator tracker",
        "https://dronexl.co/tracker/drone-delivery/operators/zipline/"),
    "dronexl_sky2": ("DroneXL, Flytrex Sky2 8.8-pound payload (May 2026)",
        "https://dronexl.co/2026/05/20/flytrex-sky2-8-8-pound-payload/"),
    "axios_noise": ("Axios, Drone delivery's next challenge: noise (Aug 2026)",
        "https://www.axios.com/2026/08/26/drone-delivery-sounds-noise-amazon-wing-zipline"),
    "yanko_wing": ("Yanko Design, Wing's Walmart drones (Oct 2026)",
        "https://www.yankodesign.com/2026/10/05/wings-walmart-drones-are-coming-to-denver-and-seattle-and-they-wont-drop-your-parcels-in-the-pool/amp/"),
    "aiwiki_wing": ("aiwiki, Wing (drone delivery)", "https://aiwiki.ai/wiki/wing_aviation"),
    "cnbc_p2": ("CNBC, Zipline unveils P2 (Mar 2023)",
        "https://www.cnbc.com/2023/03/15/zipline-unveils-p2-delivery-drones-that-dock-and-recharge-autonomously.html"),
    "urgentcomm_p2": ("Urgent Communications, Zipline drone docks and charges by itself (Mar 2023)",
        "https://urgentcomm.com/2023/03/20/zipline-delivery-drone-docks-charges-by-itself/"),
    "uavorg_p2": ("uav.org, Zipline P2 Zip", "https://www.uav.org/drones/zipline-p2-zip/"),
    "wiki_zipline": ("Wikipedia, Zipline", "https://en.wikipedia.org/wiki/Zipline_(drone_delivery_company)"),
    "uavorg_mk30": ("uav.org, Amazon Prime Air MK30", "https://www.uav.org/drones/amazon-prime-air-mk30/"),
    "freightwaves_mk30": ("FreightWaves, Amazon unveils smaller, lighter delivery drone",
        "https://www.freightwaves.com/news/amazon-unveils-smaller-lighter-more-durable-delivery-drone"),
}
