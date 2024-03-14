import {WeyaElement, WeyaElementFunction,} from '../../../../../lib/weya/weya'
import {AnalysisPreferenceModel} from "../../../models/preferences"
import {Card, CardOptions} from "../../types"
import {fillPlotPreferences} from "../../../components/charts/utils"
import {ROUTER} from '../../../app'
import {DataLoader} from '../../../components/loader'
import {CardWrapper} from "../chart_wrapper/card"
import metricsCache from "./cache"
import {Indicator} from "../../../models/run";


export class DistributedMetricsCard extends Card {
    private readonly uuid: string
    private readonly width: number
    private series: Indicator[]
    private preferenceData: AnalysisPreferenceModel
    private elem: HTMLDivElement
    private lineChartContainer: WeyaElement
    private loader: DataLoader
    private chartWrapper: CardWrapper
    private sparkLineContainer: WeyaElement

    constructor(opt: CardOptions) {
        super(opt)

        this.uuid = opt.uuid
        this.width = opt.width
        this.loader = new DataLoader(async (force) => {
            let analysisData = await  metricsCache.getAnalysis(this.uuid).get(force)
            this.series = analysisData.series
            this.preferenceData = await metricsCache.getPreferences(this.uuid).get(force)

            this.preferenceData.series_preferences = fillPlotPreferences(this.series, this.preferenceData.series_preferences)
        })
    }

    getLastUpdated(): number {
        return metricsCache.getAnalysis(this.uuid).lastUpdated
    }

    async render($: WeyaElementFunction) {
        this.elem = $('div', '.labml-card.labml-card-action', {on: {click: this.onClick}}, $ => {
            $('h3','.header', 'Distributed Metrics')
            this.loader.render($)
            this.lineChartContainer = $('div', '')
            this.sparkLineContainer = $('div', '')
        })

        try {
            await this.loader.load()

            this.chartWrapper = new CardWrapper({
                elem: this.elem,
                preferenceData: this.preferenceData,
                series: this.series,
                lineChartContainer: this.lineChartContainer,
                sparkLinesContainer: this.sparkLineContainer,
                width: this.width
            })

            this.chartWrapper.render()
        } catch (e) {
        }
    }

    async refresh() {
        try {
            await this.loader.load(true)
            this.chartWrapper?.updateData(this.series, null, this.preferenceData)
            this.chartWrapper?.render()
        } catch (e) {
        }
    }

    onClick = () => {
        ROUTER.navigate(`/run/${this.uuid}/merged_distributed`)
    }
}