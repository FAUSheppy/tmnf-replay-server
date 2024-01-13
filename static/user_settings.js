/* event listener for all sliders */
const sliders = Array.from(document.getElementsByClassName("form-check-input"))

/* safety switch -> never run set before get */
var sliders_set = false

/* defer */
sliders_load_all()

/* get initial values & set listeners */
function sliders_load_all(){
    Promise.all(sliders.map(s => {
        fetch("/update-user-settings?key=" + s.id, { credentials: "include" }).then(response => {
            response.text().then(data => {
                if(data == "True"){
                    s.checked = true
                }
            })
        })
        s.addEventListener("change", submit)
    })).then(
        sliders_set = true
    )
}

/* submit settings */
function submit(e){

    console.log("submit")
    if(!sliders_set){
        return
    }

    const s = e.target
    console.log(s)
    const json_data = JSON.stringify({ payload : [ { key : s.id, value : s.checked } ] })
    console.log(json_data)
    fetch("/update-user-settings", { 
                method: "POST",
                credentials: "include",
                headers: {'Content-Type': 'application/json'},
                body: json_data
            }
    ).then(response => {})
}
