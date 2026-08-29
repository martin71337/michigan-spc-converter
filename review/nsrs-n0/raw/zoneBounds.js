$(document).ready(function () {

    fetch('json_data/zoneBounds.json')
        .then(data => data.json())
        .then(data2 => {

            const formattedData = Object.keys(data2).map(key => {
                const obj = data2[key];
                return { ...obj, ZoneCode: key };
              });
            console.log(formattedData);

            $('#zoneBounds').DataTable({
                "data": formattedData,
                "language": {
                    "search": "",
                    "searchPlaceholder": "Filter records..."
                },
                "pageLength": 10,
                "lengthMenu": [ [10, 25, 50, 100, -1], [10, 25, 50, 100, "All"] ],
                scrollY: '75vh',
                scrollCollapse: true,
                scrollX: '100%',
                columnDefs: [
                    { targets: '_all', className: 'dt-left' },
                ],
                "columns": [
                    { 
                        "data" : "Zone code", "title" : "Zone code"
                    },
                    { 
                        "data" : "Zone abrv", "title" : "Zone abrv"
                    },
                    { 
                        "data" : "Zone name", "title" : "Zone name"
                    },
                    { 
                        "data" : "Min lat (deg)", "title" : "Min lat (deg)",
                        createdCell: function (td) {
                            td.style.backgroundColor = '#e0e0e0';
                        }
                    },
                    { 
                        "data" : "Min lon east (deg)", "title" : "Min lon east (deg)",
                        createdCell: function (td) {
                            td.style.backgroundColor = '#e0e0e0';
                        }
                    },
                    { 
                        "data" : "Min lon west (deg)", "title" : "Min lon west (deg)",
                        createdCell: function (td) {
                            td.style.backgroundColor = '#e0e0e0';
                        }
                    },
                    { 
                        "data" : "Max lat (deg)", "title" : "Max lat (deg)"
                    },
                    { 
                        "data" : "Max lon east (deg)", "title" : "Max lon east (deg)"
                    },
                    { 
                        "data" : "Max lon west (deg)", "title" : "Max lon west (deg)"
                    },
                    { 
                        "data" : "Min northing (m)", "title" : "Min northing (m)",
                        createdCell: function (td) {
                            td.style.backgroundColor = '#e0e0e0';
                        }
                    },
                    { 
                        "data" : "Min easting (m)", "title" : "Min easting (m)",
                        createdCell: function (td) {
                            td.style.backgroundColor = '#e0e0e0';
                        }
                    },
                    { 
                        "data" : "Max northing (m)", "title" : "Max northing (m)"
                    },
                    { 
                        "data" : "Max easting (m)", "title" : "Max easting (m)"
                    },
                    { 
                        "data" : "Min northing (ift)", "title" : "Min northing (ift)",
                        createdCell: function (td) {
                            td.style.backgroundColor = '#e0e0e0';
                        }
                    },
                    { 
                        "data" : "Min easting (ift)", "title" : "Min easting (ift)",
                        createdCell: function (td) {
                            td.style.backgroundColor = '#e0e0e0';
                        }
                    },
                    { 
                        "data" : "Max northing (ift)", "title" : "Max northing (ift)"
                    },
                    { 
                        "data" : "Max easting (ift)", "title" : "Max easting (ift)"
                    },
                ],

                columnDefs: [
                    // { 
                    //     targets:[10,11,12,13],
                    //     render: function(data) {
                    //         return '<div style="text-align: right;">' + data + '</div>';
                    //     }
                    // }
                ]
            });
        })
    

    
});